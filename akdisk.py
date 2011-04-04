#!/usr/bin/env python2.7

from __future__ import division
import sys
import os
import argparse
import struct
import wave
import array
import string
import fnmatch
import json
import errno

__author__ = 'Stephen Norum <stephen@mybunnyhug.org>'
__version__ = 1.0

def mkdir_p(path):
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

def underline(s, ul='='):
    return '\n'.join((s, ul * len(s)))

def full_strip(s):
    clean = ''.join(c for c in s if c in string.printable)
    return clean.strip()

def clean_name(s):
    s = full_strip(s)
    s = s.replace(':', '_')
    s = s.replace('/', ':')
    return s

def parse_0000_file(path):
    struct_fmt = (
        'x'     # Padding
        '16s'   # Name
        'x'     # Padding
        '14s'   # Path
    )
    struct_size = struct.calcsize(struct_fmt)
    name_path_dict = {}
    with open(os.path.join(path, '0000'), 'rb') as f:
        try:
            while True:
                (name, name_path) = struct.unpack(struct_fmt, f.read(struct_size))
                name_path_dict[full_strip(name_path)] = clean_name(name)
        except struct.error:
            pass
    return name_path_dict

class YamahaSample(object):
    def __init__(self, path, name='', abs_name=''):
        self.path = path
        self.name = name
        self.abs_name = abs_name
        self._framerate = None
        self._data = None

    def __repr__(self):
        return 'YamahaSample({!r}, name={!r})'.format(self.path, self.name)
    
    @property
    def fullname(self):
        return '-'.join((self.abs_name, self.name))

    @property
    def framerate(self):
        if not self._framerate:
            with open(self.path, 'rb') as f:
                f.seek(0x28)
                self._framerate = struct.unpack('>H', f.read(2))[0]
        return self._framerate

    @property
    def data(self):
        if not self._data:
            with open(self.path, 'rb') as f:
                f.seek(0x200)
                self._data = array.array('H', f.read())
            self._data.byteswap()
        return self._data
    
    def dump_wave(self, path):
        w = wave.open(path, 'wb')
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(self.framerate)
        w.writeframes(self.data)
        w.close()

class YamahaVolume(object):
    def __init__(self, path, abs_name='', name=''):
        self.path = path
        self.name = name
        self.abs_name = abs_name
        self._samples = []
        self._sample_bank = []
        self._smpl_name_path_dict = {}

    def __repr__(self):
        return 'YamahaVolume({!r}, name={!r})'.format(self.path, self.name)

    @property
    def fullname(self):
        return '-'.join((self.abs_name, self.name))

    @property
    def sample_dir_path(self):
        return os.path.join(self.path, 'SMPL')
    
    @property
    def smpl_name_path_dict(self):
        if not self._smpl_name_path_dict:
            self._smpl_name_path_dict = parse_0000_file(self.sample_dir_path)
        return self._smpl_name_path_dict

    @property
    def samples(self):
        if not self._samples:
            self._samples = [
                YamahaSample(os.path.join(self.sample_dir_path, k), v, k)
                for k, v in self.smpl_name_path_dict.iteritems()
            ]
        return self._samples

    @property
    def sample_bank(self):
        if not self._sample_bank:
            self._sample_bank = []
            sbnk_dir = os.path.join(self.path, 'SBNK')
            for filename in os.listdir(sbnk_dir):
                if fnmatch.fnmatch(filename, 'F*'):
                    with open(os.path.join(sbnk_dir, filename)) as f:
                        f.seek(0x32)
                        sample_name = full_strip(struct.unpack('>16s', f.read(16))[0])
                        f.seek(0x78)
                        sample_name_l, sample_name_r = (full_strip(n) for n in struct.unpack('>16s16s', f.read(32)))
                        self._sample_bank.append([sample_name, sample_name_l, sample_name_r])
        return self._sample_bank

class YamahaDisk(object):
    def __init__(self, path, abs_name):
        self.path = path
        self.abs_name = abs_name
        self._name = ''

    def __repr__(self):
        return 'YamahaDisk({!r})'.format(self.path)

    def __str__(self):
        return '{!r}: name={!r}'.format(self, self.name)

    @property
    def fullname(self):
        return '-'.join((self.abs_name, self.name))

    @property
    def path(self):
        return self._path

    @path.setter
    def path(self, value):
        self._path = value
        self._disks = None
        self._volumes = []
        self._name_path_dict = {}

    @property
    def name_path_dict(self):
        if not self._name_path_dict:
            self._name_path_dict = parse_0000_file(self.path)
        return self._name_path_dict
    
    @property
    def name(self):
        if not self._name:
            disk_name_file = [k for k, v in self.name_path_dict.iteritems() if v == '_DSKNAME'][0]
            try:
                with open(os.path.join(self.path, disk_name_file), 'rb') as f:
                    disk_name = clean_name(f.read())
            except IOError:
                disk_name = ''
            self._name = disk_name
        return self._name
    
    @property
    def volumes(self):
        if not self._volumes:
            self._volumes = []
            for k, v in sorted(self.name_path_dict.iteritems()):
                if v != '_DSKNAME':
                    vol_path = os.path.join(self.path, k)
                    self._volumes.append(YamahaVolume(vol_path, k, v))
        return self._volumes
    
class YamahaDrive(object):
    def __init__(self, path):
        self.path = path
    
    def __repr__(self):
        return 'YamahaDrive({!r})'.format(self.path)
    
    @property
    def path(self):
        return self._path
    
    @path.setter
    def path(self, value):
        self._path = value
        self._disks = None

    @property
    def drive_name(self):
        return os.path.basename(os.path.normpath(self.path))

    @property
    def disks(self):
        if not self._disks:
            disk_dirs = os.listdir(self.path)
            self._disks = [YamahaDisk(os.path.join(self.path, d), d) for d in disk_dirs]
        return self._disks

    def dump_all(self, dst_path=None):
        if not dst_path:
            dst_path = os.curdir
        dst_path = os.path.join(dst_path, self.drive_name)
        i = 1
        sample_count = sum([sum([len(v.samples) for v in d.volumes]) for d in self.disks])
        convert_str = ''
        try:
            mkdir_p(dst_path)
            for d in self.disks:
                disk_path = os.path.join(dst_path, d.fullname)
                os.mkdir(disk_path)
                for v in d.volumes:
                    volume_path = os.path.join(disk_path, v.fullname)
                    os.mkdir(volume_path)
                    with open(os.path.join(volume_path, 'sample_bank.txt'), 'w') as f:
                        json.dump(v.sample_bank, f, sort_keys=True, indent=4)
                    for s in v.samples:
                        sample_path = os.path.join(volume_path, '{}.wav'.format(s.name))
                        sys.stdout.write('\r')
                        sys.stdout.write(' ' * len(convert_str))
                        sys.stdout.write('\r')
                        convert_str = 'Converting {}/{} ({:.0%}): {!r}'.format(i, sample_count, (i / sample_count),sample_path)
                        sys.stdout.write(convert_str)
                        sys.stdout.flush()
                        s.dump_wave(sample_path)
                        i += 1
        except OSError as e:
            sys.stderr.write(str(e) + '\n')
            return 1
        print
        return 0

def process_arguments(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--version', action='version', version='%(prog)s {}'.format(__version__))
    parser.add_argument('sample_disc', help='path to sample disc')
    parser.add_argument('-o', '--output', metavar='DST', help='export sample disc to DST (default: current dir)')
    return parser.parse_args(argv)

def main(args):
    y = YamahaDrive(args.sample_disc)
    try:
        return y.dump_all(args.output)
    except KeyboardInterrupt:
        print
        return 1

if __name__ == '__main__':
    args = process_arguments()
    status = main(args)
    sys.exit(status)

