from flask import Flask, render_template, json, request
from pathlib import Path
import os
import subprocess as sp
import logging
import config.config_base as config
import time
FFMPEG_BIN = config.configs['ffmpeg_bin']
FFPROBE_BIN = config.configs['ffprobe_bin']

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
  return render_template('index.html')

class Video:
  def __init__(self, name, url, size, duration, bit_rate, codec_name, resolution_ratio, fps):
    self.name = name #标题
    self.url = url #视频url
    self.size = size #视频大小
    self.duration = duration #视频时长
    self.bit_rate = bit_rate #比特率
    self.codec_name = codec_name #编码
    self.resolution_ratio = resolution_ratio #分辨率
    self.fps = fps #帧率

class Frame:
  def __init__(self, first_frame_url, last_frame_url):
    self.first_frame_url = first_frame_url #第一帧
    self.last_frame_url = last_frame_url #最后一帧

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
@apiSuccess (Object) {String} fps 帧率.
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
            videoInfoJson = p.stdout.decode('utf8', 'ignore')
            videoInfo = json.loads(videoInfoJson)
            list.append(Video(child_file.name,
              os.path.join('static/video', child_dir.name, child_file.name),
              videoInfo['format']['size'],
              videoInfo['format']['duration'],
              videoInfo['streams'][0]['bit_rate'],
              videoInfo['streams'][0]['codec_name'],
              str(videoInfo['streams'][0]['coded_width']) + '/' + str(videoInfo['streams'][0]['coded_height']),
              videoInfo['streams'][0]['r_frame_rate']
            ))
            break
  return json.dumps(list, default=lambda o: o.__dict__, sort_keys=True, indent=4)

"""
@api {post} /api/ad 上传特效浮层
@apiName PostAdLayer
@apiGroup Video

@apiParam {String} video 视频标题.
@apiParam {String} ss 合成时间点，格式为 00:00:00.000
@apiParam {String} layer 特效浮层视频url
@apiParam {String} mask 蒙版浮层视频url

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
  seek_time_str = request.form['ss']
  layer_file = request.form['layer']
  mask_file = None
  try:
    mask_file = request.form['mask']
  except Exception as err:
    print('mask is empty')
  dir_name = os.path.join('static/video', file_name.split('.')[0])

  if seek_time_str != '00:00:00.000': #中间帧插入
    #分割视频
    #ffmpeg -y -i no_cover.mp4 -t 00:00:00.480 -c:v h264 -c:a aac start.mp4
    divide_start_command = [FFMPEG_BIN,
      '-y',
      '-i', os.path.join(dir_name, file_name),
      '-t', seek_time_str,
      '-c:v', 'h264',
      '-c:a', 'aac',
      os.path.join(dir_name, 'start.mp4')]
    dsp = sp.run(divide_start_command, capture_output=True)
    if dsp.returncode != 0:
      logging.error(dsp.stderr.decode('utf8', 'ignore'))
      return 'error'
    #ffmpeg -y -accurate_seek -ss 00:00:00.480 -i no_cover.mp4 -c:v h264 -c:a aac end.mp4
    divide_end_command = [FFMPEG_BIN,
      '-y',
      '-accurate_seek', '-ss', seek_time_str,
      '-i', os.path.join(dir_name, file_name),
      '-c:v', 'h264',
      '-c:a', 'aac',
      os.path.join(dir_name, 'end.mp4')]
    dep = sp.run(divide_end_command, capture_output=True)
    if dep.returncode != 0:
      logging.error(dep.stderr.decode('utf8', 'ignore'))
      return 'error'
    #合成广告视频
    if mask_file == None:
      #ffmpeg -y -i end.mp4 -i ad_layer.mov -filter_complex 'overlay' merged_end.mp4
      merge_ad_command = [FFMPEG_BIN,
        '-y',
        '-i', os.path.join(dir_name, 'end.mp4'),
        '-i', layer_file,
        '-filter_complex',
        'overlay',
        os.path.join(dir_name, 'merged_end.mp4')
      ]
    else:
      #ffmpeg -i layer.mp4 -i mask.mp4 -i source.mp4 -filter_complex "[0][1]alphamerge[ia];[2][ia]overlay" out.mp4
      merge_ad_command = [FFMPEG_BIN,
        '-y',
        '-i', layer_file,
        '-i', layer_file,
        '-i', os.path.join(dir_name, 'end.mp4'),
        '-filter_complex', '[0:0][1:0]alphamerge[lm];[2:0][lm]overlay[lma]',
        '-map', '[lma]', '-c:v', 'h264',
        '-map', '[2:1]', '-c:a', 'copy',
        os.path.join(dir_name, 'merged_end.mp4')
      ]

    mp = sp.run(merge_ad_command, capture_output=True)
    if mp.returncode != 0:
      logging.error(mp.stderr.decode('utf8', 'ignore'))
      return 'error'
    
    #合并最终预览视频
    #ffmpeg -y -i input1.mp4 -i input2.webm -i input3.avi -filter_complex '[0:0] [0:1] [1:0] [1:1] [2:0] [2:1] concat=n=3:v=1:a=1 [v] [a]' -map '[v]' -map '[a]' <编码器选项> output.mkv
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
      logging.error(mrp.stderr.decode('utf8', 'ignore'))
      return 'error'
    #删除中间状态的临时视频
    os.remove(os.path.join(dir_name, 'start.mp4'))
    os.remove(os.path.join(dir_name, 'end.mp4'))
    os.remove(os.path.join(dir_name, 'merged_end.mp4'))
  else: #起始帧插入
    #合成广告视频
    if mask_file == None:
      #ffmpeg -y -i end.mp4 -i ad_layer.mov -filter_complex 'overlay' merged_end.mp4
      merge_ad_command = [FFMPEG_BIN,
        '-y',
        '-i', os.path.join(dir_name, file_name),
        '-i', layer_file,
        '-filter_complex',
        'overlay',
        os.path.join(dir_name, 'result.mp4')
      ]
    else:
      #ffmpeg -i layer.mp4 -i mask.mp4 -i source.mp4 -filter_complex "[0][1]alphamerge[ia];[2][ia]overlay" out.mp4
      merge_ad_command = [FFMPEG_BIN,
        '-y',
        '-i', layer_file,
        '-i', mask_file,
        '-i', os.path.join(dir_name, file_name),
        '-filter_complex', '[0:0][1:0]alphamerge[lm];[2:0][lm]overlay[lma]',
        '-map', '[lma]', '-c:v', 'h264',
        os.path.join(dir_name, 'result.mp4')
      ]
      
    mp = sp.run(merge_ad_command, capture_output=True)
    if mp.returncode != 0:
      logging.error(mp.stderr.decode('utf8', 'ignore'))
      return 'error'
  
  #取最终预览视频信息
  ffprobe_command = [FFPROBE_BIN,
    '-v', 'quiet',
    '-print_format', 'json',
    '-show_format',
    '-show_streams',
    '-i', os.path.join(dir_name, 'result.mp4')
  ]
  pp = sp.run(ffprobe_command, capture_output=True)
  videoInfoJson = pp.stdout.decode('utf8', 'ignore')
  videoInfo = json.loads(videoInfoJson)
  videoClass = Video('result.mp4',
    os.path.join(dir_name, 'result.mp4'),
    videoInfo['format']['size'],
    videoInfo['format']['duration'],
    videoInfo['streams'][0]['bit_rate'],
    videoInfo['streams'][0]['codec_name'],
    str(videoInfo['streams'][0]['coded_width']) + '/' + str(videoInfo['streams'][0]['coded_height']),
    videoInfo['streams'][0]['r_frame_rate']
  )
  return json.dumps(videoClass, default=lambda o: o.__dict__, sort_keys=True, indent=4)

"""
@api {post} /api/frame 获取帧
@apiName GefFrame
@apiGroup Video

@apiParam {String} video 视频文件url

@apiSuccess {String} first_frame 第一帧.
@apiSuccess {String} last_frame 最后一帧.
"""
@app.route('/api/frame', methods=['POST'])
def frame():
  # videoFile = request.files.get('video')
  video_file = request.form['video']

  #取视频信息
  ffprobe_command = [FFPROBE_BIN,
    '-v', 'quiet',
    '-print_format', 'json',
    '-show_format',
    '-show_streams',
    '-i', video_file
  ]
  pp = sp.run(ffprobe_command, capture_output=True)
  videoInfoJson = pp.stdout.decode('utf8', 'ignore')
  videoInfo = json.loads(videoInfoJson)
  nb_frames = int(videoInfo['streams'][0]['nb_frames'])
  last_frame_index = nb_frames - 1
  #取第一帧
  now = int(round(time.time() * 1000))
  first_frame_url = os.path.join('static', 'img','first-%d.png' % now)
  #ffmpeg -y -i video.mp4 -f image2 -vframes 1 first.png
  get_first_frame_command = [FFMPEG_BIN,
    '-y',
    '-i', video_file,
    '-f', 'image2',
    '-vframes', '1',
    first_frame_url
  ]
  gffp = sp.run(get_first_frame_command, capture_output=True)
  if gffp.returncode != 0:
    logging.error(gffp.stderr.decode('utf8', 'ignore'))
    return 'error'
  #取最后一帧
  now = int(round(time.time() * 1000))
  last_frame_url = os.path.join('static', 'img', 'last-%d.png' % now)
  #ffmpeg -y -i video.mp4 -vf "select='eq(n,LAST_FRAME_INDEX)'" -f image2 -vframes 1 first.png
  get_last_frame_command = [FFMPEG_BIN,
    '-y',
    '-i', video_file,
    '-vf', "select='eq(n,%d)'" % last_frame_index,
    '-f', 'image2',
    '-vframes', '1',
    last_frame_url
  ]
  glfp = sp.run(get_last_frame_command, capture_output=True)
  if glfp.returncode != 0:
    logging.error(glfp.stderr.decode('utf8', 'ignore'))
    return 'error'

  #删除临时文件
  os.remove(video_file)
  
  frameClass = Frame(first_frame_url, last_frame_url)
  return json.dumps(frameClass, default=lambda o: o.__dict__, sort_keys=True, indent=4)

"""
@api {post} /api/upload 上传视频
@apiName Upload
@apiGroup Video

@apiParam {File} video 视频文件

@apiSuccess {String} name 视频标题.
@apiSuccess {String} url 视频url.
@apiSuccess {Number} size 视频大小.
@apiSuccess {Number} duration 视频时长.
@apiSuccess {Number} bit_rate 比特率.
@apiSuccess {String} codec_name 编码.
@apiSuccess {String} resolution_ratio 分辨率.
"""
@app.route('/api/upload', methods=['POST'])
def upload():
  videoFile = request.files.get('video')
  now = str(round(time.time() * 1000))
  filename = '%s-%s' % (now, videoFile.filename)
  videoFile.save(os.path.join('static', 'tmp', filename))
  
  #取最终预览视频信息
  ffprobe_command = [FFPROBE_BIN,
    '-v', 'quiet',
    '-print_format', 'json',
    '-show_format',
    '-show_streams',
    '-i', os.path.join('static', 'tmp', filename)
  ]
  pp = sp.run(ffprobe_command, capture_output=True)
  videoInfoJson = pp.stdout.decode('utf8', 'ignore')
  videoInfo = json.loads(videoInfoJson)
  videoClass = Video(now,
    os.path.join('static', 'tmp', filename),
    videoInfo['format']['size'],
    videoInfo['format']['duration'],
    videoInfo['streams'][0]['bit_rate'],
    videoInfo['streams'][0]['codec_name'],
    str(videoInfo['streams'][0]['coded_width']) + '/' + str(videoInfo['streams'][0]['coded_height']),
    videoInfo['streams'][0]['r_frame_rate']
  )
  return json.dumps(videoClass, default=lambda o: o.__dict__, sort_keys=True, indent=4)