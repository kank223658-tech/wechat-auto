# -*- coding: utf-8 -*-
"""
苹果微信音效引擎
================
职责：
  1. 加载三种音效（打字声、删除声、微信发送声），返回 16bit 单声道数组；
     三种音效一律来自 sounds/ 目录下的真实音效文件（type/delete/send，正确的苹果音效）；
  2. 把音效数组转成可被 winsound 播放的 WAV 字节（实时播放用）；
  3. AudioTrack：把一串「(音效数组, 起始秒)」事件按时间轴拼成整轨，供 ffmpeg 混流进成品视频；
  4. 提供 ffmpeg 音频混流辅助函数。

音效来源：
  - 若 sounds_dir 下存在 type.wav / delete.wav / send.wav（或 .mp3，mp3 用 ffmpeg 解码），则加载使用；
  - 打字/删除/发送声一律使用真实音效文件，不再 numpy 合成（旧的近似音效已删除）。

依赖：numpy（必须）。winsound 仅在 Windows 实时播放时用到（由调用方导入）。
"""

import math
import os
import random
import shutil
import subprocess
import tempfile
import wave

# 统一采样率：16bit 单声道
SAMPLE_RATE = 44100

try:
    import numpy as np
    _HAS_NUMPY = True
except Exception:                       # noqa: BLE001
    np = None
    _HAS_NUMPY = False


def _normalize(x, peak=0.9):
    """把信号归一化到峰值 peak（避免合成时削波）。"""
    if np is None or x is None or not x.size:
        return x
    m = float(np.max(np.abs(x))) if x.size else 0.0
    if m > 0:
        x = x / m * peak
    return x


def _to_int16(x):
    """float 信号转 16bit 整数数组。"""
    x = np.clip(x, -1.0, 1.0)
    return (x * 32767).astype(np.int16)


# ----------------------------------------------------------------------------
# 二、加载 / 合成，返回 {name: int16 数组}
# ----------------------------------------------------------------------------

# ffmpeg 单次调用超时（秒）。防止 ffmpeg 意外卡死导致整个流程无限挂起
# （历史问题：编码/混流阶段没有任何超时保护，一旦 ffmpeg 卡住整条视频无法收尾）。
FFMPEG_TIMEOUT = 900


def _safe_remove(path):
    """尽力删除文件，失败（不存在/被占用）静默忽略。"""
    try:
        if path and os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _find_ffmpeg():
    """返回可用的 ffmpeg 可执行文件路径；找不到返回 None。

    优先用 PATH 里的 ffmpeg；找不到时回退到 imageio-ffmpeg 自带的内置 ffmpeg
    （与 main.py 的 ffmpeg 解析逻辑一致，保证真实音效一定能被加载）。
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        try:
            from imageio_ffmpeg import get_ffmpeg_exe as _bundled_ffmpeg
            ffmpeg = _bundled_ffmpeg()
        except Exception:                   # noqa: BLE001
            return None
    return ffmpeg if ffmpeg else None


def _decode_mp3(path):
    """用 ffmpeg 把 mp3 解码成临时 wav；找不到 ffmpeg 或解码失败返回 None。"""
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", path, "-ac", "1",
                        "-ar", str(SAMPLE_RATE), tmp], check=True, timeout=FFMPEG_TIMEOUT)
        return tmp
    except Exception:                   # noqa: BLE001
        return None


def _load_wav(path):
    """读取单声道 WAV 为 float32（-1~1）；失败返回 None。"""
    try:
        with wave.open(path, "rb") as wf:
            n = wf.getnframes()
            sr = wf.getframerate()
            ch = wf.getnchannels()
            data = np.frombuffer(wf.readframes(n), dtype=np.int16).astype(np.float32)
            if ch > 1:
                data = data.reshape(-1, ch).mean(axis=1)
            data = data / 32768.0
            # 若采样率不同，线性重采样到统一 SAMPLE_RATE
            if sr != SAMPLE_RATE and sr > 0 and data.size:
                idx = np.linspace(0, data.size - 1, int(data.size * SAMPLE_RATE / sr))
                data = np.interp(idx, np.arange(data.size), data).astype(np.float32)
            return data
    except Exception:                   # noqa: BLE001
        return None


def load_or_synth(sounds_dir):
    """返回 {name: int16 单声道数组}。

    读取 sounds_dir 下的真实音效（.wav 直接读，.mp3/mp4 等其它格式走 ffmpeg 解码）；
    三种音效一律来自真实文件（旧的 numpy 合成已删除）。numpy 不可用时返回空 dict。

    额外加载 `continuous_type`（持续打字声）：高速打字（TYPE_SPEED ≥ 阈值）时，
    把一段连打合并成一条「原生持续打字音轨」按敲击时长裁剪后使用，不再逐键叠加
    单个打字音效。优先读 continuous_type.wav/.mp3，缺省回退到用户提供的
    sounds/连续打字声.mp4（ffmpeg 解出音频轨）。无此音源则不断言该键，调用方自然回退逐键。
    """
    if not _HAS_NUMPY:
        return {}
    result = {}
    if sounds_dir:
        for name in ("type", "delete", "send"):
            wav_path = os.path.join(sounds_dir, name + ".wav")
            mp3_path = os.path.join(sounds_dir, name + ".mp3")
            arr = None
            if os.path.isfile(wav_path):
                arr = _load_wav(wav_path)
            elif os.path.isfile(mp3_path):
                tmp = _decode_mp3(mp3_path)
                if tmp:
                    arr = _load_wav(tmp)
                    try:
                        os.remove(tmp)
                    except OSError:
                        pass
            if arr is not None and arr.size:
                result[name] = _to_int16(_normalize(arr, 0.95))
        # ---- 持续打字声（原生音轨）----
        ct_paths = [
            os.path.join(sounds_dir, "continuous_type.wav"),
            os.path.join(sounds_dir, "continuous_type.mp3"),
            os.path.join(sounds_dir, "连续打字声.mp4"),   # 用户提供的原生持续打字音轨
        ]
        ct_arr = None
        for p in ct_paths:
            if not os.path.isfile(p):
                continue
            try:
                ct_arr = load_audio_float(p)     # wav 直接读，其余走 ffmpeg 解码成 mono
            except Exception:                    # noqa: BLE001
                ct_arr = None
            if ct_arr is not None and ct_arr.size:
                break
        if ct_arr is not None and ct_arr.size:
            result["continuous_type"] = _to_int16(_normalize(ct_arr, 0.95))
    return result


def load_audio_float(path):
    """把任意音频解码为 float32 单声道数组（SAMPLE_RATE）；失败返回 None。

    .wav 直接读；其它格式（mp3 等）用 ffmpeg 解码成临时 wav 再读。
    """
    if not path or not os.path.isfile(path):
        return None
    if path.lower().endswith(".wav"):
        return _load_wav(path)
    ffmpeg = _find_ffmpeg()
    if not ffmpeg:
        return None
    try:
        fd, tmp = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        subprocess.run([ffmpeg, "-y", "-loglevel", "error", "-i", path,
                        "-ac", "1", "-ar", str(SAMPLE_RATE), tmp], check=True,
                       timeout=FFMPEG_TIMEOUT)
        arr = _load_wav(tmp)
        try:
            os.remove(tmp)
        except OSError:
            pass
        return arr
    except Exception:                   # noqa: BLE001
        return None


def process_bgm(input_path, max_seconds=None):
    """对背景音乐做「轻量去重」：只保留听感几乎无感、不改变音乐气质的小变换，
    让同一首音乐每次生成后的字节/频谱特征略有不同，规避简单指纹/哈希匹配。

    相比完整 AudioDeDupTool 大幅精简，并去掉会明显破坏音乐听感的处理（颤音、多频带
    随机 EQ、随机陷波、全局微变速、粉噪混入），只保留：
      - 极轻微的整体音量漂移（±0.5dB）；
      - 极轻微的变调（±0.5%，约 0.09 个半音，听感几乎无感但能把频谱峰值整体搬移，
        是内容级指纹逃逸的关键）；
      - 随机输出采样率 / 抖动（仅影响编码字节，不影响听感）。
    听感与原曲基本一致。

    max_seconds: 只处理开头这么多秒（0/None 表示整段），配合主流程循环/裁剪可避免
                 反复转码整段长音乐，缩短生成耗时。
    返回 float32 单声道数组（SAMPLE_RATE）；ffmpeg 不可用、文件缺失或处理失败返回 None。
    """
    ffmpeg = _find_ffmpeg()
    if not ffmpeg or not input_path or not os.path.isfile(input_path):
        return None
    out_wav = None
    try:
        vol = random.uniform(-0.5, 0.5)              # 音量漂移 ±0.5dB（极轻，几乎无感）
        pitch = 1 + random.uniform(-0.005, 0.005)    # 变调 ±0.5%（≈0.09 半音，几乎无感）
        dither = random.choice(["triangular", "rectangular"])
        out_rate = random.choice(["44100", "48000"])
        # 变调（保持时长）：asetrate 提速 → atempo 拉回，频谱整体搬移、时长不变
        chain = ["aformat=sample_rates=48000:channel_layouts=mono",
                 "volume=%.2fdB" % vol,
                 "aresample=48000,asetrate=48000*%.6f,atempo=%.6f,aresample=48000"
                 % (pitch, 1.0 / pitch)]
        fc = "[0:a]" + ",".join(chain) + "[aout]"
        fd, out_wav = tempfile.mkstemp(suffix=".wav")
        os.close(fd)
        cmd = [ffmpeg, "-y", "-loglevel", "error"]
        if max_seconds:
            cmd += ["-t", "%.3f" % float(max_seconds)]     # 只读开头一段，缩短处理耗时
        cmd += ["-i", input_path,
                "-filter_complex", fc, "-map", "[aout]",
                "-map_metadata", "-1",
                "-c:a", "pcm_s16le", "-ar", out_rate, "-dither_method", dither, out_wav]
        subprocess.run(cmd, check=True, timeout=FFMPEG_TIMEOUT)
        arr = _load_wav(out_wav)
        try:
            os.remove(out_wav)
        except OSError:
            pass
        return arr
    except Exception:                   # noqa: BLE001
        if out_wav:
            try:
                os.remove(out_wav)
            except OSError:
                pass
        return None


def trim_leading_silence(arr, threshold=0.015, keep_s=0.0):
    """裁掉数组开头的静音段，让背景音乐从「有声音的地方」立即开始。

    背景音乐文件（如 背景音乐.mp3）常在开头带 1s+ 的静音前奏，导致铺入视频后
    音乐要过一会儿才真正出声（显得「来得慢」）。此函数找到第一个超过 threshold
    的采样点，把其之前的静音整段裁掉，使音乐从视频第一帧即可听见。

    threshold: 判定为静音的峰值阈值（相对满幅 ~1.0）。
    keep_s:   在裁剪点之前额外保留的秒数（0 表示从第一个有声采样处开始）；
              保留一小段可与后续 loop_to_length 的短头淡入配合，避免切入咔哒。
    返回 float32 mono 数组；数组为空、整段全静音或无需裁剪时原样返回。
    """
    if arr is None or not arr.size:
        return arr
    arr = arr.astype(np.float32)
    above = np.abs(arr) > threshold
    if not above.any():
        return arr
    idx = int(np.argmax(above))          # 第一个超过 threshold 的采样点
    if idx <= 0:
        return arr
    start = max(0, idx - int(keep_s * SAMPLE_RATE))
    return arr[start:]


def loop_to_length(arr, n, fade_s=0.008):
    """把 mono 数组循环/截断到 n 个采样，循环接缝做短交叉淡化，避免咔哒声。

    fade_s: 循环接缝与头尾淡入淡出的秒数（0 表示不做淡化）。
    """
    if arr is None or not arr.size or n <= 0:
        return None
    arr = arr.astype(np.float32)
    length = len(arr)
    if length >= n:
        return arr[:n].copy()
    fade = min(int(fade_s * SAMPLE_RATE), length // 2) if fade_s > 0 else 0
    if fade < 1:
        reps = int(math.ceil(float(n) / length))
        return np.tile(arr, reps)[:n].copy()
    out = np.empty(n, dtype=np.float32)
    pos = 0
    first = True
    while pos < n:
        if first:
            seg_len = min(length, n - pos)
            out[pos:pos + seg_len] = arr[:seg_len]
            pos += seg_len
            first = False
        else:
            remain = n - pos
            if remain <= fade:
                out[pos:] = arr[:remain] * np.linspace(1.0, 0.0, remain, dtype=np.float32)
                pos = n
                break
            # 交叉淡化接缝：前一段尾部淡出 × 新一段头部淡入
            seam = out[pos - fade:pos].copy()
            head = arr[:fade]
            out[pos - fade:pos] = seam * np.linspace(1.0, 0.0, fade, dtype=np.float32) \
                + head * np.linspace(0.0, 1.0, fade, dtype=np.float32)
            seg_len = min(length, remain)
            body = arr[fade:seg_len]
            out[pos:pos + len(body)] = body
            pos += len(body)
    # 头尾轻微淡入淡出，避免成品视频开始/结束处咔哒
    fin = min(int(0.01 * SAMPLE_RATE), n)
    if fin:
        out[:fin] *= np.linspace(0.0, 1.0, fin, dtype=np.float32)
    fout = min(int(0.01 * SAMPLE_RATE), n)
    if fout:
        out[-fout:] *= np.linspace(1.0, 0.0, fout, dtype=np.float32)
    return out


def wav_bytes(arr, sr=SAMPLE_RATE):
    """把 int16 数组转成 winsound 可用的 WAV 字节（SND_MEMORY）。"""
    if arr is None or not arr.size:
        return b""
    data = arr.astype(np.int16).tobytes()
    import io
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(sr)
        wf.writeframes(data)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# 三、AudioTrack：把一串事件拼成整轨
# ----------------------------------------------------------------------------

class AudioTrack:
    """把 [(int16 数组, 起始秒), ...] 按时间轴叠加拼成整轨。"""

    def __init__(self, sr=SAMPLE_RATE):
        self.sr = sr
        self._events = []
        self._background = None      # float32 单声道铺底数组（含自身增益），供整轨叠加

    def add(self, arr, start_sec):
        """在 start_sec 处叠加一段音效（arr 为 int16 单声道）。"""
        if arr is None or not arr.size:
            return
        self._events.append((arr.astype(np.float32) / 32768.0, float(start_sec)))

    def set_background(self, arr_f32, gain=1.0):
        """设置一条铺底背景（float32 单声道，~[-1,1]），按 gain 缩放后在整轨叠加。

        与 add() 的事件不同：背景以整段铺在视频全长上，不受事件位置影响。
        """
        if arr_f32 is None or not arr_f32.size:
            return
        self._background = arr_f32.astype(np.float32) * float(gain)

    def duration(self):
        """返回整轨时长（秒）。"""
        if not self._events:
            return 0.0
        return max(s + len(a) / self.sr for a, s in self._events)

    def render(self, duration=None, gain=1.0):
        """输出长度为 duration 秒的整轨 float32（未归一，供写 wav 前 clip）。

        gain 只作用于事件音效；铺底背景已在 set_background 里按自身增益缩放，在此之后叠加。
        """
        if not self._events and self._background is None:
            return None
        dur = duration if duration is not None else self.duration()
        n = max(1, int(dur * self.sr))
        out = np.zeros(n, dtype=np.float32)
        for arr, s in self._events:
            start = int(s * self.sr)
            if start >= n:
                break
            seg = arr
            end = min(start + len(seg), n)
            out[start:end] += seg[:end - start]
        out *= gain
        if self._background is not None:
            b = self._background
            m = min(len(b), n)
            out[:m] += b[:m]
        return out

    def write_wav(self, path, duration=None, gain=1.0):
        """把整轨写成 16bit WAV 文件；无事件直接略过并返回 False。"""
        out = self.render(duration, gain)
        if out is None:
            return False
        out = np.clip(out, -1.0, 1.0)
        pcm = (out * 32767).astype(np.int16)
        with wave.open(path, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(self.sr)
            wf.writeframes(pcm.tobytes())
        return True


# ----------------------------------------------------------------------------
# 四、ffmpeg 音频混流：给无声 MP4 加音轨
# ----------------------------------------------------------------------------

def ffmpeg_mux_audio(ffmpeg, video_path, audio_wav, out_path, audio_bitrate="128k"):
    """把 audio_wav 音轨混流进 video_path，写 out_path。视频流拷贝不重编码。"""
    cmd = [ffmpeg, "-y", "-loglevel", "error",
           "-i", video_path, "-i", audio_wav,
           "-c:v", "copy", "-c:a", "aac", "-b:a", audio_bitrate,
           "-shortest", "-movflags", "+faststart", out_path]
    try:
        subprocess.run(cmd, check=True, timeout=FFMPEG_TIMEOUT)
    except subprocess.TimeoutExpired:
        # 超时：清理写了一半的成品，避免留下残缺文件；由调用方决定是否保留无声视频
        _safe_remove(out_path)
        raise