import atexit
import ctypes
import math
import os
import random
import threading
import time
import tkinter as tk

SIZE = 20
WIDTH = 30
HEIGHT = 20
SPEED = 120
SCALE = (0, 2, 3, 5, 7, 8, 10)
WAVE_FORMAT_PCM = 1
WAVE_MAPPER = 0xFFFFFFFF
WHDR_DONE = 0x00000001


class WAVEFORMATEX(ctypes.Structure):
    _fields_ = [
        ("wFormatTag", ctypes.c_ushort),
        ("nChannels", ctypes.c_ushort),
        ("nSamplesPerSec", ctypes.c_uint),
        ("nAvgBytesPerSec", ctypes.c_uint),
        ("nBlockAlign", ctypes.c_ushort),
        ("wBitsPerSample", ctypes.c_ushort),
        ("cbSize", ctypes.c_ushort),
    ]


class WAVEHDR(ctypes.Structure):
    _fields_ = [
        ("lpData", ctypes.c_void_p),
        ("dwBufferLength", ctypes.c_uint),
        ("dwBytesRecorded", ctypes.c_uint),
        ("dwUser", ctypes.c_size_t),
        ("dwFlags", ctypes.c_uint),
        ("dwLoops", ctypes.c_uint),
        ("lpNext", ctypes.c_void_p),
        ("reserved", ctypes.c_size_t),
    ]


def midi(note):
    return 440.0 * 2 ** ((note - 69) / 12)


def scale_note(base, degree):
    octave, step = divmod(degree, len(SCALE))
    return base + octave * 12 + SCALE[step]


def clamp(value, low, high):
    return max(low, min(high, value))


def nearest(value, options):
    return min(options, key=lambda option: abs(option - value))


def pan_gains(pan):
    angle = (clamp(pan, -1.0, 1.0) + 1.0) * math.pi / 4
    return math.cos(angle), math.sin(angle)


def soft_clip(value):
    return math.tanh(value)


def tone_event(
    start,
    duration,
    notes,
    amp,
    pan=0.0,
    vibrato=0.0,
    attack=0.05,
    release=0.15,
    partials=((1.0, 1.0),),
    chorus=0.0,
):
    if not isinstance(notes, (list, tuple)):
        notes = [notes]
    gain_l, gain_r = pan_gains(pan)
    norm = len(notes) * (sum(abs(weight) for _, weight in partials) + chorus or 1.0)
    return {
        "kind": "tone",
        "start": start,
        "end": start + duration,
        "duration": duration,
        "freqs": [midi(note) for note in notes],
        "amp": amp,
        "gain_l": gain_l,
        "gain_r": gain_r,
        "vibrato": vibrato,
        "attack": attack,
        "release": release,
        "partials": partials,
        "chorus": chorus,
        "norm": norm,
    }


def percussion_event(kind, start, amp, pan=0.0):
    durations = {"kick": 0.18, "snare": 0.14, "hat": 0.045}
    gain_l, gain_r = pan_gains(pan)
    return {
        "kind": kind,
        "start": start,
        "end": start + durations[kind],
        "duration": durations[kind],
        "amp": amp,
        "gain_l": gain_l,
        "gain_r": gain_r,
    }


def chirp_event(start, duration, note_a, note_b, amp, pan=0.0):
    gain_l, gain_r = pan_gains(pan)
    return {
        "kind": "chirp",
        "start": start,
        "end": start + duration,
        "duration": duration,
        "freq_a": midi(note_a),
        "freq_b": midi(note_b),
        "amp": amp,
        "gain_l": gain_l,
        "gain_r": gain_r,
    }


class MusicComposer:
    def __init__(self):
        self.rng = random.Random()
        self.bpm = 132
        self.beat = 60 / self.bpm
        self.step = self.beat / 4
        self.bar = self.beat * 4
        self.snake_length = 3
        self.energy = 0.35
        self.next_bar = 0.0
        self.section_bar = 0
        self.degree = 0
        self.pan_flip = 1
        self.motif = [0, 2, 3, 4, 3, 1, 2, None]
        self.arp_pattern = [0, 2, 1, 3, 2, 4, 1, 3, 0, 3, 1, 4, 2, 1, 3, 4]

    def set_snake_length(self, length):
        self.snake_length = max(3, length)

    def target_bars(self):
        return 4 + max(0, self.snake_length - 3) // 2

    def ensure_events(self, end_time, events):
        while self.next_bar < end_time:
            if self.section_bar == 0:
                self.start_phrase()
            target = self.target_bars()
            degree = self.choose_degree(target)
            self.compose_bar(self.next_bar, degree, target, events)
            self.next_bar += self.bar
            self.section_bar += 1
            if self.section_bar >= self.target_bars():
                self.section_bar = 0
                self.degree = 0

    def start_phrase(self):
        self.energy = min(1.0, 0.35 + (self.snake_length - 3) * 0.035)
        self.pan_flip *= -1
        motif = []
        for index, value in enumerate(self.motif):
            if value is None and self.rng.random() < 0.55:
                motif.append(None)
                continue
            if self.rng.random() < 0.18 and index % 2 == 1:
                motif.append(None)
                continue
            base = 2 if value is None else value
            shift = self.rng.choice([-1, 0, 0, 1, 1, 2]) if index % 2 else self.rng.choice([-1, 0, 1])
            motif.append(clamp(base + shift, 0, 6))
        motif[0] = 0
        motif[4] = clamp(2 if motif[4] is None else motif[4], 0, 6)
        if self.energy > 0.75 and self.rng.random() < 0.4:
            motif[-1] = 6
        self.motif = motif

        arp = self.arp_pattern[:]
        for _ in range(4):
            a = self.rng.randrange(len(arp))
            b = self.rng.randrange(len(arp))
            arp[a], arp[b] = arp[b], arp[a]
        for index, value in enumerate(arp):
            if self.rng.random() < 0.16:
                arp[index] = clamp(value + self.rng.choice([-1, 1]), 0, 4)
        self.arp_pattern = arp

    def choose_degree(self, target):
        if self.section_bar == 0:
            degree = 0
        elif self.section_bar >= target - 1:
            degree = 0
        elif self.section_bar >= target - 2:
            degree = self.rng.choice([4, 6, 3])
        else:
            transitions = {
                0: [5, 3, 2, 6],
                2: [6, 3, 5],
                3: [0, 6, 4, 5],
                4: [0, 3, 6],
                5: [2, 3, 0],
                6: [0, 5, 2, 3],
            }
            choices = transitions.get(self.degree, [0, 3, 5, 6])
            if self.section_bar % 4 == 3:
                choices += [3, 5]
            if self.energy > 0.7 and self.rng.random() < 0.25:
                choices += [2, 4]
            options = list(dict.fromkeys(choices))
            degree = self.rng.choice(options)
        self.degree = degree
        return degree

    def compose_bar(self, start, degree, target, events):
        chord = [scale_note(57, degree + offset) for offset in (0, 2, 4, 6)]
        arp_notes = [scale_note(69, degree + offset) for offset in (0, 2, 4, 6)] + [scale_note(69, degree + 8)]
        events.append(
            tone_event(
                start,
                self.bar * 0.98,
                chord + [chord[0] + 12],
                0.16 + self.energy * 0.05,
                pan=-0.14 * self.pan_flip,
                vibrato=0.2,
                attack=0.22,
                release=0.28,
                partials=((1.0, 1.0), (2.0, 0.16), (0.5, 0.08)),
                chorus=0.08,
            )
        )

        for index, pick in enumerate(self.arp_pattern):
            if index % 4 and self.rng.random() < 0.08:
                continue
            note = arp_notes[pick]
            if self.energy > 0.8 and index in (3, 11):
                note += 12
            events.append(
                tone_event(
                    start + index * self.step,
                    self.step * (0.82 if index % 4 else 0.96),
                    note,
                    0.07 + self.energy * 0.03 + (0.03 if index % 4 == 0 else 0.0),
                    pan=(0.42 if index % 2 else -0.42) * self.pan_flip,
                    vibrato=5.6,
                    attack=0.05,
                    release=0.2,
                    partials=((1.0, 1.0), (2.0, 0.22)),
                    chorus=0.05,
                )
            )

        if self.section_bar == target - 2:
            line = [14, 15, 16, 15, 14, 13, 12, 13]
        elif self.section_bar == target - 1:
            line = [14, 13, 12, 11, 10, 9, 8, 7]
        else:
            palette = [degree + 7, degree + 8, degree + 9, degree + 10, degree + 11, degree + 13, degree + 14]
            line = []
            for index in range(8):
                slot = self.motif[(index + self.section_bar) % len(self.motif)]
                if slot is None and index % 2 == 1:
                    line.append(None)
                    continue
                slot = 2 if slot is None else slot
                note_degree = palette[slot]
                if index % 4 == 0:
                    chord_targets = [degree + 7, degree + 9, degree + 11, degree + 13]
                    note_degree = nearest(note_degree, chord_targets)
                if self.energy > 0.82 and index in (3, 7):
                    note_degree += 7
                line.append(note_degree)

        for index, note_degree in enumerate(line):
            if note_degree is None:
                continue
            note = scale_note(57, note_degree)
            notes = note
            if self.energy > 0.85 and index in (0, 4):
                notes = [note, scale_note(57, note_degree + 2)]
            events.append(
                tone_event(
                    start + index * (self.beat / 2),
                    self.beat * (0.48 if index % 4 else 0.52),
                    notes,
                    0.14 + self.energy * 0.06 + (0.03 if index % 4 == 0 else 0.0),
                    pan=(-0.16 + 0.05 * index) * self.pan_flip,
                    vibrato=6.0,
                    attack=0.04,
                    release=0.24,
                    partials=((1.0, 1.0), (2.0, 0.28)),
                    chorus=0.09,
                )
            )

        walk = [degree, degree + 4, degree + (7 if self.rng.random() < 0.5 else 5), degree + (1 if self.rng.random() < 0.5 else 2)]
        if self.section_bar == target - 2:
            walk[-1] = 6
        elif self.section_bar == target - 1:
            walk[-1] = 0
        for index, bass_degree in enumerate(walk):
            events.append(
                tone_event(
                    start + index * self.beat,
                    self.beat * 0.9,
                    scale_note(33, bass_degree),
                    0.18 + self.energy * 0.05,
                    pan=-0.04,
                    attack=0.03,
                    release=0.18,
                    partials=((1.0, 1.0), (0.5, 0.22), (2.0, 0.14)),
                )
            )

        self.compose_drums(start, target, events)

    def compose_drums(self, start, target, events):
        events.append(percussion_event("kick", start, 0.8))
        events.append(percussion_event("kick", start + self.beat * 2, 0.82))
        if self.energy > 0.45:
            events.append(percussion_event("kick", start + self.beat * 1.5, 0.42))
        if self.energy > 0.72 and self.rng.random() < 0.45:
            events.append(percussion_event("kick", start + self.beat * 2.5, 0.5))

        events.append(percussion_event("snare", start + self.beat, 0.3))
        events.append(percussion_event("snare", start + self.beat * 3, 0.32))

        hat_count = 8 if self.energy < 0.68 else 16
        hat_step = self.bar / hat_count
        for index in range(hat_count):
            if hat_count == 16 and index % 4 == 3 and self.rng.random() < 0.2:
                continue
            amp = 0.05 + 0.02 * (index % 2) + (0.02 if hat_count == 16 and index % 4 == 0 else 0.0)
            events.append(
                percussion_event(
                    "hat",
                    start + index * hat_step,
                    amp,
                    -0.3 if index % 2 == 0 else 0.3,
                )
            )

        if self.section_bar == target - 1:
            fill_start = start + self.bar - self.beat / 2
            for index in range(4):
                events.append(percussion_event("snare", fill_start + index * self.step, 0.1 + index * 0.04))


class AudioEngine:
    def __init__(self):
        self.available = False
        self.closed = False
        self.running = False
        self.paused = False
        self.rate = 22050
        self.chunk = 0.05
        self.buffer_target = 2
        self.position = 0.0
        self.snake_length = 3
        self.events = []
        self.pending_effects = []
        self.pending = []
        self.lock = threading.Lock()
        self.thread = None
        self.handle = None
        self.delay_1_l = [0.0] * int(self.rate * 0.23)
        self.delay_1_r = [0.0] * int(self.rate * 0.23)
        self.delay_2_l = [0.0] * int(self.rate * 0.41)
        self.delay_2_r = [0.0] * int(self.rate * 0.41)
        self.delay_1_i = 0
        self.delay_2_i = 0
        self.composer = MusicComposer()
        self.winmm = ctypes.WinDLL("winmm") if os.name == "nt" else None
        if not self.winmm:
            return
        self._bind_api()
        try:
            self._open()
        except OSError:
            return
        self.available = True
        self.running = True
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _bind_api(self):
        self.winmm.waveOutOpen.argtypes = [
            ctypes.POINTER(ctypes.c_void_p),
            ctypes.c_uint,
            ctypes.POINTER(WAVEFORMATEX),
            ctypes.c_size_t,
            ctypes.c_size_t,
            ctypes.c_uint,
        ]
        self.winmm.waveOutOpen.restype = ctypes.c_uint
        self.winmm.waveOutPrepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), ctypes.c_uint]
        self.winmm.waveOutPrepareHeader.restype = ctypes.c_uint
        self.winmm.waveOutWrite.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), ctypes.c_uint]
        self.winmm.waveOutWrite.restype = ctypes.c_uint
        self.winmm.waveOutUnprepareHeader.argtypes = [ctypes.c_void_p, ctypes.POINTER(WAVEHDR), ctypes.c_uint]
        self.winmm.waveOutUnprepareHeader.restype = ctypes.c_uint
        self.winmm.waveOutPause.argtypes = [ctypes.c_void_p]
        self.winmm.waveOutPause.restype = ctypes.c_uint
        self.winmm.waveOutRestart.argtypes = [ctypes.c_void_p]
        self.winmm.waveOutRestart.restype = ctypes.c_uint
        self.winmm.waveOutReset.argtypes = [ctypes.c_void_p]
        self.winmm.waveOutReset.restype = ctypes.c_uint
        self.winmm.waveOutClose.argtypes = [ctypes.c_void_p]
        self.winmm.waveOutClose.restype = ctypes.c_uint

    def _open(self):
        fmt = WAVEFORMATEX(
            wFormatTag=WAVE_FORMAT_PCM,
            nChannels=2,
            nSamplesPerSec=self.rate,
            nAvgBytesPerSec=self.rate * 4,
            nBlockAlign=4,
            wBitsPerSample=16,
            cbSize=0,
        )
        handle = ctypes.c_void_p()
        result = self.winmm.waveOutOpen(ctypes.byref(handle), WAVE_MAPPER, ctypes.byref(fmt), 0, 0, 0)
        if result:
            raise OSError(result)
        self.handle = handle

    def set_snake_length(self, length):
        with self.lock:
            self.snake_length = max(3, length)

    def play_eat(self):
        if not self.available:
            return
        with self.lock:
            start = self.position + 0.005
            self.pending_effects.extend(
                [
                    chirp_event(start + 0.01, 0.12, 79, 88, 0.22, -0.15),
                    chirp_event(start + 0.05, 0.18, 83, 95, 0.18, 0.18),
                    tone_event(
                        start + 0.03,
                        0.16,
                        [88, 95],
                        0.1,
                        pan=0.08,
                        vibrato=8.0,
                        attack=0.02,
                        release=0.25,
                        partials=((1.0, 1.0), (2.0, 0.18)),
                        chorus=0.04,
                    ),
                ]
            )

    def set_paused(self, paused):
        self.paused = paused
        if not self.available:
            return
        if paused:
            self.winmm.waveOutPause(self.handle)
        else:
            self.winmm.waveOutRestart(self.handle)

    def close(self):
        if self.closed:
            return
        self.closed = True
        if not self.available:
            return
        self.running = False
        if self.thread:
            self.thread.join(timeout=1)
        self.winmm.waveOutReset(self.handle)
        self._reap(done_only=False)
        self.winmm.waveOutClose(self.handle)

    def _loop(self):
        while self.running:
            self._reap()
            if not self.paused:
                while self.running and not self.paused and len(self.pending) < self.buffer_target:
                    raw = self._render_chunk()
                    self._queue(raw)
                    with self.lock:
                        self.position += self.chunk
            time.sleep(0.005)

    def _render_chunk(self):
        count = int(self.rate * self.chunk)
        left = [0.0] * count
        right = [0.0] * count
        with self.lock:
            snake_length = self.snake_length
            if self.pending_effects:
                self.events.extend(self.pending_effects)
                self.pending_effects.clear()
        self.events.sort(key=lambda event: event["start"])
        self.composer.set_snake_length(snake_length)
        self.composer.ensure_events(self.position + self.chunk, self.events)
        end = self.position + self.chunk
        active = []
        for event in self.events:
            if event["end"] <= self.position:
                continue
            if event["start"] < end:
                self._mix_event(left, right, self.position, event)
            if event["end"] > end:
                active.append(event)
        self.events = active
        self._apply_delay(left, right)

        frames = bytearray()
        for l_value, r_value in zip(left, right):
            l_int = int(clamp(soft_clip(l_value) * 30000, -32767, 32767))
            r_int = int(clamp(soft_clip(r_value) * 30000, -32767, 32767))
            frames.extend(l_int.to_bytes(2, "little", signed=True))
            frames.extend(r_int.to_bytes(2, "little", signed=True))
        return bytes(frames)

    def _mix_event(self, left, right, chunk_start, event):
        if event["kind"] == "tone":
            self._mix_tone(left, right, chunk_start, event)
        elif event["kind"] == "kick":
            self._mix_kick(left, right, chunk_start, event)
        elif event["kind"] == "snare":
            self._mix_snare(left, right, chunk_start, event)
        elif event["kind"] == "hat":
            self._mix_hat(left, right, chunk_start, event)
        elif event["kind"] == "chirp":
            self._mix_chirp(left, right, chunk_start, event)

    def _mix_tone(self, left, right, chunk_start, event):
        start_index = max(0, int((event["start"] - chunk_start) * self.rate))
        end_index = min(len(left), int((event["end"] - chunk_start) * self.rate) + 1)
        attack = max(event["duration"] * event["attack"], 1 / self.rate)
        release = max(event["duration"] * event["release"], 1 / self.rate)
        for index in range(start_index, end_index):
            t = chunk_start + index / self.rate - event["start"]
            if t < 0 or t > event["duration"]:
                continue
            env = 1.0
            if t < attack:
                env *= math.sin(t / attack * math.pi / 2)
            tail = event["duration"] - t
            if tail < release:
                env *= math.sin(max(0.0, tail / release) * math.pi / 2)
            mod = 0.02 * math.sin(2 * math.pi * event["vibrato"] * t) if event["vibrato"] else 0.0
            sample = 0.0
            for freq in event["freqs"]:
                voice = 0.0
                for mult, weight in event["partials"]:
                    voice += weight * math.sin(2 * math.pi * freq * mult * t + mod * mult)
                if event["chorus"]:
                    voice += event["chorus"] * math.sin(2 * math.pi * freq * 1.004 * t + mod * 1.3 + 0.6)
                sample += voice
            sample *= event["amp"] * env / event["norm"]
            left[index] += sample * event["gain_l"]
            right[index] += sample * event["gain_r"]

    def _mix_kick(self, left, right, chunk_start, event):
        start_index = max(0, int((event["start"] - chunk_start) * self.rate))
        end_index = min(len(left), int((event["end"] - chunk_start) * self.rate) + 1)
        phase = 0.0
        for index in range(start_index, end_index):
            t = chunk_start + index / self.rate - event["start"]
            x = clamp(t / event["duration"], 0.0, 1.0)
            freq = 150 - 95 * (x ** 0.6)
            phase += 2 * math.pi * freq / self.rate
            env = (1 - x) ** 4
            sample = (math.sin(phase) + 0.35 * math.sin(phase * 2.2)) * env * event["amp"]
            left[index] += sample * 0.7
            right[index] += sample * 0.7

    def _mix_snare(self, left, right, chunk_start, event):
        freqs = (180, 330, 540, 870, 1230)
        start_index = max(0, int((event["start"] - chunk_start) * self.rate))
        end_index = min(len(left), int((event["end"] - chunk_start) * self.rate) + 1)
        for index in range(start_index, end_index):
            t = chunk_start + index / self.rate - event["start"]
            x = clamp(t / event["duration"], 0.0, 1.0)
            env = (1 - x) ** 5
            sample = sum(math.sin(2 * math.pi * freq * t + freq * 0.01) for freq in freqs) / len(freqs)
            sample *= env * event["amp"]
            left[index] += sample * event["gain_l"]
            right[index] += sample * event["gain_r"]

    def _mix_hat(self, left, right, chunk_start, event):
        freqs = (2400, 3600, 5100)
        start_index = max(0, int((event["start"] - chunk_start) * self.rate))
        end_index = min(len(left), int((event["end"] - chunk_start) * self.rate) + 1)
        for index in range(start_index, end_index):
            t = chunk_start + index / self.rate - event["start"]
            x = clamp(t / event["duration"], 0.0, 1.0)
            env = (1 - x) ** 7
            sample = sum(math.sin(2 * math.pi * freq * t + freq * 0.002) for freq in freqs) / len(freqs)
            sample *= env * event["amp"]
            left[index] += sample * event["gain_l"]
            right[index] += sample * event["gain_r"]

    def _mix_chirp(self, left, right, chunk_start, event):
        start_index = max(0, int((event["start"] - chunk_start) * self.rate))
        end_index = min(len(left), int((event["end"] - chunk_start) * self.rate) + 1)
        sweep = event["freq_b"] - event["freq_a"]
        for index in range(start_index, end_index):
            t = chunk_start + index / self.rate - event["start"]
            x = clamp(t / event["duration"], 0.0, 1.0)
            env = math.sin(x * math.pi) ** 1.6
            phase = 2 * math.pi * (event["freq_a"] * t + 0.5 * sweep * t * t / event["duration"])
            sample = (math.sin(phase) + 0.25 * math.sin(phase * 2.01)) * env * event["amp"]
            left[index] += sample * event["gain_l"]
            right[index] += sample * event["gain_r"]

    def _apply_delay(self, left, right):
        for index in range(len(left)):
            d1l = self.delay_1_l[self.delay_1_i]
            d1r = self.delay_1_r[self.delay_1_i]
            d2l = self.delay_2_l[self.delay_2_i]
            d2r = self.delay_2_r[self.delay_2_i]
            dry_l = left[index]
            dry_r = right[index]
            wet_l = dry_l + d1l * 0.22 + d2r * 0.08
            wet_r = dry_r + d1r * 0.22 + d2l * 0.08
            self.delay_1_l[self.delay_1_i] = dry_l + d1l * 0.35
            self.delay_1_r[self.delay_1_i] = dry_r + d1r * 0.35
            self.delay_2_l[self.delay_2_i] = dry_l + d2l * 0.24
            self.delay_2_r[self.delay_2_i] = dry_r + d2r * 0.24
            self.delay_1_i = (self.delay_1_i + 1) % len(self.delay_1_l)
            self.delay_2_i = (self.delay_2_i + 1) % len(self.delay_2_l)
            left[index] = wet_l
            right[index] = wet_r

    def _queue(self, raw):
        data = ctypes.create_string_buffer(raw)
        header = WAVEHDR(
            lpData=ctypes.addressof(data),
            dwBufferLength=len(raw),
            dwBytesRecorded=0,
            dwUser=0,
            dwFlags=0,
            dwLoops=0,
            lpNext=None,
            reserved=0,
        )
        size = ctypes.sizeof(header)
        self.winmm.waveOutPrepareHeader(self.handle, ctypes.byref(header), size)
        self.winmm.waveOutWrite(self.handle, ctypes.byref(header), size)
        self.pending.append((data, header))

    def _reap(self, done_only=True):
        keep = []
        for data, header in self.pending:
            if done_only and not (header.dwFlags & WHDR_DONE):
                keep.append((data, header))
                continue
            self.winmm.waveOutUnprepareHeader(self.handle, ctypes.byref(header), ctypes.sizeof(header))
        self.pending = keep


class SnakeGame:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Snake")
        self.canvas = tk.Canvas(
            self.root,
            width=WIDTH * SIZE,
            height=HEIGHT * SIZE,
            bg="#111",
            highlightthickness=0,
        )
        self.canvas.pack()
        self.root.bind("<Key>", self.on_key)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.audio = AudioEngine()
        atexit.register(self.audio.close)
        self.after_id = None
        self.paused = False
        self.restart()

    def restart(self):
        self.direction = (1, 0)
        self.next_direction = (1, 0)
        self.snake = [(5, 10), (4, 10), (3, 10)]
        self.food = self.new_food()
        self.alive = True
        self.paused = False
        self.audio.set_paused(False)
        self.audio.set_snake_length(len(self.snake))
        self.draw()
        self.schedule_tick()

    def new_food(self):
        while True:
            food = (random.randrange(WIDTH), random.randrange(HEIGHT))
            if food not in self.snake:
                return food

    def schedule_tick(self):
        if self.after_id is None and self.alive and not self.paused:
            self.after_id = self.root.after(SPEED, self.tick)

    def toggle_pause(self):
        if not self.alive:
            return
        self.paused = not self.paused
        self.audio.set_paused(self.paused)
        self.draw()
        if not self.paused:
            self.schedule_tick()

    def on_key(self, event):
        key = event.keysym.lower()
        moves = {
            "up": (0, -1),
            "down": (0, 1),
            "left": (-1, 0),
            "right": (1, 0),
            "w": (0, -1),
            "s": (0, 1),
            "a": (-1, 0),
            "d": (1, 0),
        }
        if key == "p":
            self.toggle_pause()
            return
        if not self.alive and key == "r":
            self.restart()
            return
        if self.paused:
            return
        move = moves.get(key)
        if move and move != (-self.direction[0], -self.direction[1]):
            self.next_direction = move

    def tick(self):
        self.after_id = None
        if not self.alive or self.paused:
            return
        self.direction = self.next_direction
        x, y = self.snake[0]
        dx, dy = self.direction
        head = (x + dx, y + dy)
        body = self.snake if head == self.food else self.snake[:-1]

        if (
            head[0] < 0
            or head[0] >= WIDTH
            or head[1] < 0
            or head[1] >= HEIGHT
            or head in body
        ):
            self.alive = False
            self.draw()
            return

        self.snake.insert(0, head)
        if head == self.food:
            self.audio.play_eat()
            self.audio.set_snake_length(len(self.snake))
            self.food = self.new_food()
        else:
            self.snake.pop()

        self.draw()
        self.schedule_tick()

    def draw(self):
        self.canvas.delete("all")
        fx, fy = self.food
        self.block(fx, fy, "#ff5252")
        for index, (x, y) in enumerate(self.snake):
            self.block(x, y, "#5cff8d" if index == 0 else "#2ecc71")
        if not self.alive:
            self.root.title(f"Game Over | Score: {len(self.snake) - 3} | Press R")
            self.canvas.create_text(
                WIDTH * SIZE // 2,
                HEIGHT * SIZE // 2,
                text="Game Over\nPress R",
                fill="white",
                font=("Consolas", 20, "bold"),
            )
            return
        if self.paused:
            self.root.title(f"Snake | Score: {len(self.snake) - 3} | Paused")
            self.canvas.create_text(
                WIDTH * SIZE // 2,
                HEIGHT * SIZE // 2,
                text="Paused\nPress P",
                fill="white",
                font=("Consolas", 20, "bold"),
            )
            return
        self.root.title(f"Snake | Score: {len(self.snake) - 3}")

    def block(self, x, y, color):
        pad = 2
        self.canvas.create_rectangle(
            x * SIZE + pad,
            y * SIZE + pad,
            (x + 1) * SIZE - pad,
            (y + 1) * SIZE - pad,
            fill=color,
            outline="",
        )

    def close(self):
        if self.after_id is not None:
            self.root.after_cancel(self.after_id)
        self.audio.close()
        self.root.destroy()

    def run(self):
        self.root.mainloop()


def main():
    SnakeGame().run()


if __name__ == "__main__":
    main()
