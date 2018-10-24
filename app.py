from flask import Flask, render_template, json, request
from pathlib import Path
import os
import subprocess as sp
import logging
import config.config_base as config
FFMPEG_BIN = config.configs['ffmpeg_bin']
FFPROBE_BIN = config.configs['ffprobe_bin']

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
  return render_template('index.html')

class Video:
  def __init__(self, name, url, size, duration, bit_rate, codec_name, resolution_ratio):
    self.name = name #标题
    self.url = url #视频url
    self.size = size #视频大小
    self.duration = duration #视频时长
    self.bit_rate = bit_rate #比特率
    self.codec_name = codec_name #编码
    self.resolution_ratio = resolution_ratio #分辨率

"""
@api {get} /api/list 获取视频列表
@apiName GetVideoList
@apiGroup Video

@apiSuccess {Object[]} body http body
@apiSuccess (Object) {String} name 视频标题.
@apiSuccess (Object) {String} url 视频url.
@apiSuccess (Object) {Number} size 视频大小.
@apiSuccess (Object) {Number} duration 视频时长.
@apiSuccess (Object) {Number} bit_rate 比特率.
@apiSuccess (Object) {String} codec_name 编码.
@apiSuccess (Object) {String} resolution_ratio 分辨率.
"""
@app.route('/api/list', methods=['GET'])
def list():
  list = []
  pd = Path('static/video')
  for child_dir in pd.iterdir():
    if child_dir.is_dir():
      pf = Path(os.path.join('static/video', child_dir.name))
      for child_file in pf.iterdir():
        if not child_file.is_dir():
          if child_file.name.find(child_dir.name) != -1:
            ffprobe_command = [FFPROBE_BIN,
              '-v', 'quiet',
              '-print_format', 'json',
              '-show_format',
              '-show_streams',
              '-i', os.path.join('static/video', child_dir.name, child_file.name)
            ]
            p = sp.run(ffprobe_command, capture_output=True)
            videoInfoJson = p.stdout.decode('ascii')
            videoInfo = json.loads(videoInfoJson)
            list.append(Video(child_file.name,
              os.path.join('static/video', child_dir.name, child_file.name),
              videoInfo['format']['size'],
              videoInfo['format']['duration'],
              videoInfo['streams'][0]['bit_rate'],
              videoInfo['streams'][0]['codec_name'],
              str(videoInfo['streams'][0]['coded_width']) + '×' + str(videoInfo['streams'][0]['coded_height'])
            ))
            break
  return json.dumps(list, default=lambda o: o.__dict__, sort_keys=True, indent=4)

"""
@api {post} /api/ad 上传特效浮层
@apiName PostAdLayer
@apiGroup Video

@apiParam {String} video 视频标题.
@apiParam {String} ss 合成时间点，格式为 00:00:00.000
@apiParam {File} ad_layer 特效浮层的序列帧文件

@apiSuccess {String} name 视频标题.
@apiSuccess {String} url 视频url.
@apiSuccess {Number} size 视频大小.
@apiSuccess {Number} duration 视频时长.
@apiSuccess {Number} bit_rate 比特率.
@apiSuccess {String} codec_name 编码.
@apiSuccess {String} resolution_ratio 分辨率.
"""
@app.route('/api/ad', methods=['POST'])
def ad():
  file_name = request.form['video']
  dir_name = 'static/video/%s' % file_name.split('.')[0]
  seek_time_str = request.form['ss']
  file = request.files['ad_layer']
  file.save(os.path.join(dir_name, file.filename))
  # 分割视频
  # ffmpeg -y -i no_cover.mp4 -t 00:00:00.480 -c:v h264 -c:a aac start.mp4
  divide_start_command = [FFMPEG_BIN,
    '-y',
    '-i', os.path.join(dir_name, file_name),
    '-t', seek_time_str,
    '-c:v', 'h264',
    '-c:a', 'aac',
    os.path.join(dir_name, 'start.mp4')]
  dsp = sp.run(divide_start_command, capture_output=True)
  if dsp.returncode != 0:
    logging.error(dsp.stderr.decode('ascii'))
    return 'error'
  # ffmpeg -y -accurate_seek -ss 00:00:00.480 -i no_cover.mp4 -c:v h264 -c:a aac end.mp4
  divide_end_command = [FFMPEG_BIN,
    '-y',
    '-accurate_seek', '-ss', seek_time_str,
    '-i', os.path.join(dir_name, file_name),
    '-c:v', 'h264',
    '-c:a', 'aac',
    os.path.join(dir_name, 'end.mp4')]
  dep = sp.run(divide_end_command, capture_output=True)
  if dep.returncode != 0:
    logging.error(dep.stderr.decode('ascii'))
    return 'error'
  # 合成广告视频
  # ffmpeg -y -i end.mp4 -i ad_layer.mov -filter_complex 'overlay' merged_end.mp4
  merge_ad_command = [FFMPEG_BIN,
    '-y',
    '-i', '%s/end.mp4' % dir_name,
    '-i', os.path.join(dir_name, file.filename),
    '-filter_complex',
    'overlay',
    os.path.join(dir_name, 'merged_end.mp4')
  ]
  mp = sp.run(merge_ad_command, capture_output=True)
  if mp.returncode != 0:
    logging.error(mp.stderr.decode('ascii'))
    return 'error'
  # 合并最终预览视频
  # ffmpeg -y -i input1.mp4 -i input2.webm -i input3.avi -filter_complex '[0:0] [0:1] [1:0] [1:1] [2:0] [2:1] concat=n=3:v=1:a=1 [v] [a]' -map '[v]' -map '[a]' <编码器选项> output.mkv
  merge_result_command = [FFMPEG_BIN,
    '-y',
    '-i', os.path.join(dir_name, 'start.mp4'),
    '-i', os.path.join(dir_name, 'merged_end.mp4'),
    '-filter_complex', '[0:0] [0:1] [1:0] [1:1] concat=n=2:v=1:a=1 [v] [a]',
    '-map', '[v]',
    '-map', '[a]',
    '-c:v', 'h264',
    '-c:a', 'aac',
    os.path.join(dir_name, 'result.mp4')
  ]
  mrp = sp.run(merge_result_command, capture_output=True)
  if mrp.returncode != 0:
    logging.error(mrp.stderr.decode('ascii'))
    return 'error'
  # 删除中间状态的临时视频
  os.remove(os.path.join(dir_name, 'start.mp4'))
  os.remove(os.path.join(dir_name, 'end.mp4'))
  os.remove(os.path.join(dir_name, 'merged_end.mp4'))
  #取最终预览视频信息
  ffprobe_command = [FFPROBE_BIN,
    '-v', 'quiet',
    '-print_format', 'json',
    '-show_format',
    '-show_streams',
    '-i', os.path.join(dir_name, 'result.mp4')
  ]
  pp = sp.run(ffprobe_command, capture_output=True)
  videoInfoJson = pp.stdout.decode('ascii')
  videoInfo = json.loads(videoInfoJson)
  videoClass = Video('result.mp4',
    os.path.join(dir_name, 'result.mp4'),
    videoInfo['format']['size'],
    videoInfo['format']['duration'],
    videoInfo['streams'][0]['bit_rate'],
    videoInfo['streams'][0]['codec_name'],
    str(videoInfo['streams'][0]['coded_width']) + '×' + str(videoInfo['streams'][0]['coded_height'])
  )
  return json.dumps(videoClass, default=lambda o: o.__dict__, sort_keys=True, indent=4)
