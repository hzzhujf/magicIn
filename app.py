from flask import Flask, render_template, json
from pathlib import Path
import os

app = Flask(__name__)

@app.route('/', methods=['GET'])
def home():
  return render_template('index.html')

@app.route('/api/list', methods=['GET'])
def list():
  class Video:
    def __init__(self, title, url):
      self.title = title
      self.url = url

  list = []
  pd = Path('static/video')
  for childDir in pd.iterdir():
    if childDir.is_dir():
      pf = Path(os.path.join('static/video', childDir.name))
      for childFile in pf.iterdir():
        if not childFile.is_dir():
          if childFile.name.find(childDir.name) != -1:
            list.append(Video(childFile.name, os.path.join('static/video', childDir.name, childFile.name)))
            break
  return json.dumps(list, default=lambda o: o.__dict__, sort_keys=True, indent=4)


