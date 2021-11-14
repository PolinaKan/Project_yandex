import math

from PyQt5.QtWidgets import (QApplication, QWidget, QMainWindow, QFileDialog)
from PyQt5.QtCore import QRectF, QPointF
from PyQt5.QtGui import (QPaintEvent, QPainter, QColor, QPen, QBrush, QMouseEvent, QKeyEvent)
import sys
import pyaudio
import sqlite3
from array import array
from ui import Ui_MainWindow


# класс для работы с файлами
class Record:
    def __init__(self, time: int, key: int, press: bool):
        self.time = time
        self.key = key
        self.press = press

    # сохранение файла
    def save(self, offset: int = 0):
        return str(self.time - offset) + " " + str(self.key) + " " + str(self.press)

    def db(self):
        return {"time": self.time, "key": self.key, "press": (1 if self.press else 0)}

    # загрузка файла для проигрывания
    def load(self, s: str):
        data = s.split(' ')
        self.time = int(data[0])
        self.key = int(data[1])
        self.press = (data[2] == "True")


# класс для рисования клавиш
class Key:
    def __init__(self, octaves: int, octave: int, n: int):
        # n: 0,2,4,5,7,9,11 - whites
        # n: 1,3,6,8,10 - blacks
        # общее количество октав
        self.octaves = octaves
        # октава для определенной клавиши
        self.octave = octave
        self.mousehot = False
        self.keyhot = False
        self.playhot = False
        self.oldhot = False
        # номер клавиши в октаве (0 - 11)
        self.kn = n
        # номер клавиши
        self.id = octave * 12 + n
        # индивидуальное название клавишы
        self.name = chr(octave * 12 + self.kn + 65)
        self.v = 0
        # номер клавишы
        if (n == 1) or (n == 3) or (n == 6) or (n == 8) or (n == 10):
            self.black = True
            if n < 4:
                self.n = (n - 1) // 2
            else:
                self.n = ((n - 6) // 2) + 2
        else:
            self.black = False
            if n < 5:
                self.n = n // 2
            else:
                self.n = ((n - 5) // 2) + 3

    # определение размера клавишы
    def rect(self, rect: QRectF) -> QRectF:
        w = rect.width() / (7 * self.octaves)
        kw = w / 2
        x = self.octave * 7 * w
        if self.black:
            x += kw + self.n * w + kw / 2
            if self.n > 1:
                x += w
            return QRectF(x, 0, kw, rect.height() / 2)
        else:
            x += self.n * w
            return QRectF(x, 0, w, rect.height())

    # определение частоты для клавиш
    def freq(self):
        id = self.id + 12 * 3
        return math.pow(2, (id - 49) / 12) * 440

    # проверка на активацию клавиши
    def ishot(self):
        return self.keyhot or self.mousehot or self.playhot

    # выставляет флаг (playhot) для проигрывания звука
    def play(self, pressed: bool):
        if pressed != self.playhot:
            self.playhot = pressed
            return True
        return False

    # рисование в соответствии с текущим состоянием клавишы
    def paint(self, rect: QRectF, p: QPainter):
        r = self.rect(rect)
        if self.black:
            p.setPen(QColor(255, 255, 255))
            p.setBrush(QColor(0, 0, 0))
            # когда клавиша нажата - перекрашиваем
            if self.ishot():
                p.setBrush(QColor(128, 128, 128))
            p.drawRect(r)
            p.setPen(QColor(255, 255, 255))
            p.setBrush(QColor(255, 255, 255))
        else:
            p.setPen(QColor(0, 0, 0))
            p.setBrush(QColor(255, 255, 255))
            # когда клавиша нажата - перекрашиваем
            if self.ishot():
                p.setBrush(QColor(128, 128, 128))
            p.drawRect(r)
            p.setPen(QColor(0, 0, 0))
            p.setBrush(QColor(0, 0, 0))
        br = p.boundingRect(r, self.name)
        pt = r.center()
        pt.setY(r.bottom() - 10)
        br.moveCenter(pt)
        p.drawText(br, self.name)

    # обновление флага активности
    def mouse(self, rect: QRectF, pos: QPointF):
        hot = False
        if not (pos is None) and self.rect(rect).contains(pos):
            hot = True
        if hot != self.mousehot:
            self.mousehot = hot
            return True
        return False

    # обновление статуса нажатия клавиши
    def key(self, text, pressed):
        hot = False
        if text.lower() == self.name.lower():
            if pressed != self.keyhot:
                self.keyhot = pressed
                return True
        return False


# класс для работы с основным окном (обработка клавиш синтезатора, работа с файлами)
class Piano(QMainWindow, Ui_MainWindow):
    def __init__(self):
        super().__init__()
        self.setupUi(self)
        # количество октав
        octaves = 3
        self.keys = []
        self.record = []
        self.play = []
        self.playoffset = None
        # частота оцифровки (количество отсчетов в секунду аудиопотока)
        self.samplerate = 48000
        self.n = 0
        self.map = dict()
        for octave in range(octaves):
            for n in range(12):
                k = Key(octaves, octave, n)
                self.map[k.id] = k
                self.keys.append(k)
        self.action_Exit.triggered.connect(self.close)
        self.action_New.triggered.connect(self.file_new)
        self.action_Open.triggered.connect(self.file_open)
        self.action_Save.triggered.connect(self.file_save)

    # обработка события мыши
    def mouse(self, pos: QPointF):
        update = False
        black = False
        rect = QRectF(self.rect())
        for k in self.keys:
            if k.black:
                update = k.mouse(rect, pos) or update
                black = black or k.mousehot
        for k in self.keys:
            if not k.black:
                update = k.mouse(rect, None if black else pos) or update
        if update:
            self.update()

    # обработка нажатия клавиши (pressed = true - нажата, = false - не нажата)
    def key(self, text, pressed):
        update = False
        for k in self.keys:
            update = k.key(text, pressed) or update
        if update:
            self.update()

    # клавиша нажата
    def keyPressEvent(self, a0):
        super().keyPressEvent(a0)
        self.key(a0.text(), True)

    # клавиша не нажата
    def keyReleaseEvent(self, a0):
        super().keyReleaseEvent(a0)
        self.key(a0.text(), False)

    # мышка нажата
    def mousePressEvent(self, a0: QMouseEvent):
        super().mousePressEvent(a0)
        self.mouse(a0.pos())

    # перемещение мышки
    def mouseMoveEvent(self, a0: QMouseEvent):
        super().mouseMoveEvent(a0)
        self.mouse(a0.pos())

    # мышка не нажата
    def mouseReleaseEvent(self, a0: QMouseEvent):
        super().mouseReleaseEvent(a0)
        self.mouse(None)

    # создание нового файла
    def file_new(self):
        self.record = []

    # открытие файла, чтение из базы данных в массив play
    def file_open(self):
        file, filter = QFileDialog.getOpenFileName(self, "Open a piano record", "", "Piano (*.piano)")
        if len(file):
            self.play = []
            self.playoffset = None
            plays = []
            conn = sqlite3.connect(file)
            c = conn.cursor()
            c.execute('SELECT keyid, time, press FROM piano ORDER BY time')
            for k in c:
                r = Record(key=k[0], time=k[1], press=k[2])
                plays.append(r)
            conn.close()
            self.play = plays

    # сохранение в фалй и запись в базу данных
    def file_save(self):
        file, filter = QFileDialog.getSaveFileName(self, "Save a piano record", "", "Piano (*.piano)")
        if len(file):
            conn = sqlite3.connect(file)
            offset = 0
            if len(self.record):
                offset = self.record[0].time
            c = conn.cursor()
            c.execute('CREATE TABLE IF NOT EXISTS piano(keyid integer NOT NULL, time integer '
                      'NOT NULL, press integer NOT NULL)')
            c.execute('DELETE FROM piano')
            for rec in self.record:
                c.execute('INSERT INTO piano(keyid, time, press) VALUES(:key, :time, :press)', rec.db())
            conn.commit()
            conn.close()

    # перерисовка всего окна
    def paintEvent(self, event):
        p = QPainter(self)
        for k in self.keys:
            if not k.black:
                k.paint(QRectF(self.rect()), p)
        for k in self.keys:
            if k.black:
                k.paint(QRectF(self.rect()), p)

    # проигрывание звука клавиш
    def sound(self, frame_count):
        b = bytearray(frame_count)
        n = self.n
        vattack = 0.003
        vdecay = 0.003
        if len(self.play):
            if self.playoffset is None:
                self.playoffset = n
            update = False
            while len(self.play) and (self.play[0].time < (n - self.playoffset + frame_count)):
                p = self.play[0]
                update = self.map[p.key].play(p.press) or update
                self.play.pop(0)
            if update:
                self.update()
        else:
            self.playoffset = None
        q = [0 for x in range(frame_count)]
        for k in self.keys:
            freq = k.freq()
            m = freq / self.samplerate * 2 * math.pi
            hot = k.ishot()
            if hot != k.oldhot:
                self.record.append(Record(n, k.id, hot))
                k.oldhot = hot
            if k.ishot() or (k.v > 0):
                for x in range(frame_count):
                    kv = k.v + (vattack if k.ishot() else -vdecay)
                    kv = min(max(kv, 0), 1)
                    if k.v == 0 and kv > 0:
                        k.x = 0
                        k.q = 1
                    v = math.sin(k.x * m) * kv * k.q
                    k.x += 1
                    k.v = kv
                    if k.q > 0:
                        k.q -= min(k.q, 10 ** -5 * 6)  # 0.00006
                    q[x] += v
        for x in range(frame_count):
            q[x] = int(min(max(-32768, q[x] * 5000), 32767))
        self.n += frame_count
        return bytes(array('h', q)), False


# pyaudio вызывает эту функцию
def callback(in_data, frame_count, time_info, status):
    return piano.sound(frame_count)


if __name__ == '__main__':
    global piano
    app = QApplication(sys.argv)
    piano = Piano()
    piano.show()
    p = pyaudio.PyAudio()
    stream = p.open(format=p.get_format_from_width(2),
                    channels=1,
                    rate=piano.samplerate,
                    output=True,
                    stream_callback=callback)
    stream.start_stream()
    e = app.exec_()
    stream.stop_stream()
    exit(e)
