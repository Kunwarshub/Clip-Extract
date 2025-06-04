from flask import Flask, render_template, request, send_file
import os
import whisper
from pytubefix import YouTube
from difflib import SequenceMatcher
import subprocess

app = Flask(__name__, static_url_path="/static")
app.config['UPLOAD_FOLDER'] = "uploads"
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)



def transcribe_video(video_path):
    model = whisper.load_model("tiny")
    result = model.transcribe(video_path, verbose=True)
    return result['segments']


def download_video(url, save_path):
    yt = YouTube(url)
    print("YT title: ", yt.title)
    streams = yt.streams.filter(progressive=True, file_extension='mp4')
    print("Available streams: ", streams)
    stream = streams.get_highest_resolution()
    if not stream:
        raise Exception("No suitable stream found")
    return stream.download(output_path=save_path)


def find_best_seg(prompt, segments):
    best_seg = None
    best_score = 0
    for seg in segments:
        score = SequenceMatcher(None, prompt.lower(), seg['text'].lower()).ratio()
        if score > best_score:
            best_score = score
            best_seg = seg
    return best_seg


def clip_video_ffmpeg(video_path, start_time, duration, output_path):
    command = [
        "ffmpeg",
        "-y",
        "-i", video_path,
        "-ss", str(start_time),
        "-t", str(duration),
        "-c", "copy",
        output_path
    ]
    try:
        subprocess.run(command, check=True)
        print("Clip saved to:", output_path)
    except subprocess.CalledProcessError as e:
        print("FFmpeg Error:", e)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/extractGIF", methods=["POST"])
def extractGIF():
    url = request.form.get("url", "").strip()
    prompt = request.form.get("prompt", "").strip()
    video = request.files.get("video")

    if not prompt:
        return "Error: No prompt provided", 400
    if not url and not video:
        return "Error: No video file or URL provided", 400
    if url and video and video.filename != "":
        return "Error: Provide either a video file or a YouTube URL, not both", 400

    try:
        if video and video.filename != "":
            video_path = os.path.join(app.config['UPLOAD_FOLDER'], video.filename)
            video_path = os.path.abspath(video_path).replace("\\", "/")
            video.save(video_path)
        else:
            video_path = download_video(url, app.config['UPLOAD_FOLDER'])

        print("Video path:", video_path)
        print("File exists:", os.path.exists(video_path))

        segments = transcribe_video(video_path)
        best_seg = find_best_seg(prompt, segments)

        if best_seg:
            print(f"BEST MATCH:\n [{best_seg['start']} --> {best_seg['end']}] {best_seg['text']}")
            start = best_seg["start"]
            duration = best_seg["end"] - best_seg["start"]
            clip_path = os.path.join(app.config['UPLOAD_FOLDER'], "clip.mp4")

            clip_video_ffmpeg(video_path, start, duration, clip_path)
            return send_file(clip_path, as_attachment=True)
        else:
            return "No matching segment found", 404

    except Exception as e:
        print("Error:", e)
        return "Something went wrong.", 500


if __name__ == "__main__":
    app.run(debug=True)
