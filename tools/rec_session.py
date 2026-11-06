"""Record her through the Focusrite (front inputs 1/2, ASIO) until build/lab/STOP_REC exists or max minutes pass.
Saves build/lab/sessions/<date-time>.wav (24-bit stereo, 48 kHz, true level, no normalising). Private: build/ only.

  py -3.10 rec_session.py [max_minutes]
"""
import os, sys, time, struct, datetime
os.environ.setdefault('SD_ENABLE_ASIO', '1')
import numpy as np, sounddevice as sd

HERE = os.path.dirname(os.path.abspath(__file__))
LAB = os.path.join(HERE, '..', 'build', 'lab')
OUT = os.path.join(LAB, 'sessions')
STOP = os.path.join(LAB, 'STOP_REC')
FS, CH = 48000, (0, 1)


def wav24(path, x):
    x = np.clip(x, -1, 1 - 2 ** -23)
    i = (x * 2 ** 23).astype('<i4')
    b = bytearray()
    raw = i.reshape(-1)
    b = np.frombuffer(raw.tobytes(), dtype=np.uint8).reshape(-1, 4)[:, :3].tobytes()
    with open(path + '.tmp', 'wb') as f:
        f.write(b'RIFF' + struct.pack('<I', 36 + len(b)) + b'WAVEfmt ' +
                struct.pack('<IHHIIHH', 16, 1, 2, FS, FS * 6, 6, 24) + b'data' + struct.pack('<I', len(b)) + b)
    os.replace(path + '.tmp', path)


def main():
    maxmin = float(sys.argv[1]) if len(sys.argv) > 1 else 15.0
    os.makedirs(OUT, exist_ok=True)
    if os.path.exists(STOP):
        os.remove(STOP)
    dev = [k for k, d in enumerate(sd.query_devices()) if 'focusrite usb asio' in d['name'].lower()][0]
    chunks = []
    def cb(indata, frames, t, status):
        chunks.append(indata[:, list(CH)].copy())
    t0 = time.time()
    name = datetime.datetime.now().strftime('%Y-%m-%d_%H%M%S')
    with sd.InputStream(samplerate=FS, channels=6, device=dev, dtype='float32', callback=cb, blocksize=2048):
        print('recording', name, flush=True)
        while not os.path.exists(STOP) and time.time() - t0 < maxmin * 60:
            time.sleep(0.2)
    x = np.concatenate(chunks) if chunks else np.zeros((1, 2), 'float32')
    path = os.path.join(OUT, name + '.wav')
    wav24(path, x)
    pk = float(np.abs(x).max())
    print('saved %s  %.1f s  peak %.1f dBFS' % (os.path.abspath(path), len(x) / FS, 20 * np.log10(pk + 1e-12)), flush=True)
    if os.path.exists(STOP):
        os.remove(STOP)


if __name__ == '__main__':
    main()
