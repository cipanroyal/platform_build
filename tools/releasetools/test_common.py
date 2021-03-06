#
# Copyright (C) 2015 The Android Open Source Project
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#
import os
import shutil
import tempfile
import time
import unittest
import zipfile

from hashlib import sha1

import common
import validate_target_files

KiB = 1024
MiB = 1024 * KiB
GiB = 1024 * MiB

def get_2gb_string():
  size = int(2 * GiB + 1)
  block_size = 4 * KiB
  step_size = 4 * MiB
  # Generate a long string with holes, e.g. 'xyz\x00abc\x00...'.
  for _ in range(0, size, step_size):
    yield os.urandom(block_size)
    yield '\0' * (step_size - block_size)


class CommonZipTest(unittest.TestCase):
  def _verify(self, zip_file, zip_file_name, arcname, expected_hash,
              test_file_name=None, expected_stat=None, expected_mode=0o644,
              expected_compress_type=zipfile.ZIP_STORED):
    # Verify the stat if present.
    if test_file_name is not None:
      new_stat = os.stat(test_file_name)
      self.assertEqual(int(expected_stat.st_mode), int(new_stat.st_mode))
      self.assertEqual(int(expected_stat.st_mtime), int(new_stat.st_mtime))

    # Reopen the zip file to verify.
    zip_file = zipfile.ZipFile(zip_file_name, "r")

    # Verify the timestamp.
    info = zip_file.getinfo(arcname)
    self.assertEqual(info.date_time, (2009, 1, 1, 0, 0, 0))

    # Verify the file mode.
    mode = (info.external_attr >> 16) & 0o777
    self.assertEqual(mode, expected_mode)

    # Verify the compress type.
    self.assertEqual(info.compress_type, expected_compress_type)

    # Verify the zip contents.
    entry = zip_file.open(arcname)
    sha1_hash = sha1()
    for chunk in iter(lambda: entry.read(4 * MiB), ''):
      sha1_hash.update(chunk)
    self.assertEqual(expected_hash, sha1_hash.hexdigest())
    self.assertIsNone(zip_file.testzip())

  def _test_ZipWrite(self, contents, extra_zipwrite_args=None):
    extra_zipwrite_args = dict(extra_zipwrite_args or {})

    test_file = tempfile.NamedTemporaryFile(delete=False)
    test_file_name = test_file.name

    zip_file = tempfile.NamedTemporaryFile(delete=False)
    zip_file_name = zip_file.name

    # File names within an archive strip the leading slash.
    arcname = extra_zipwrite_args.get("arcname", test_file_name)
    if arcname[0] == "/":
      arcname = arcname[1:]

    zip_file.close()
    zip_file = zipfile.ZipFile(zip_file_name, "w")

    try:
      sha1_hash = sha1()
      for data in contents:
        sha1_hash.update(data)
        test_file.write(data)
      test_file.close()

      expected_stat = os.stat(test_file_name)
      expected_mode = extra_zipwrite_args.get("perms", 0o644)
      expected_compress_type = extra_zipwrite_args.get("compress_type",
                                                       zipfile.ZIP_STORED)
      time.sleep(5)  # Make sure the atime/mtime will change measurably.

      common.ZipWrite(zip_file, test_file_name, **extra_zipwrite_args)
      common.ZipClose(zip_file)

      self._verify(zip_file, zip_file_name, arcname, sha1_hash.hexdigest(),
                   test_file_name, expected_stat, expected_mode,
                   expected_compress_type)
    finally:
      os.remove(test_file_name)
      os.remove(zip_file_name)

  def _test_ZipWriteStr(self, zinfo_or_arcname, contents, extra_args=None):
    extra_args = dict(extra_args or {})

    zip_file = tempfile.NamedTemporaryFile(delete=False)
    zip_file_name = zip_file.name
    zip_file.close()

    zip_file = zipfile.ZipFile(zip_file_name, "w")

    try:
      expected_compress_type = extra_args.get("compress_type",
                                              zipfile.ZIP_STORED)
      time.sleep(5)  # Make sure the atime/mtime will change measurably.

      if not isinstance(zinfo_or_arcname, zipfile.ZipInfo):
        arcname = zinfo_or_arcname
        expected_mode = extra_args.get("perms", 0o644)
      else:
        arcname = zinfo_or_arcname.filename
        expected_mode = extra_args.get("perms",
                                       zinfo_or_arcname.external_attr >> 16)

      common.ZipWriteStr(zip_file, zinfo_or_arcname, contents, **extra_args)
      common.ZipClose(zip_file)

      self._verify(zip_file, zip_file_name, arcname, sha1(contents).hexdigest(),
                   expected_mode=expected_mode,
                   expected_compress_type=expected_compress_type)
    finally:
      os.remove(zip_file_name)

  def _test_ZipWriteStr_large_file(self, large, small, extra_args=None):
    extra_args = dict(extra_args or {})

    zip_file = tempfile.NamedTemporaryFile(delete=False)
    zip_file_name = zip_file.name

    test_file = tempfile.NamedTemporaryFile(delete=False)
    test_file_name = test_file.name

    arcname_large = test_file_name
    arcname_small = "bar"

    # File names within an archive strip the leading slash.
    if arcname_large[0] == "/":
      arcname_large = arcname_large[1:]

    zip_file.close()
    zip_file = zipfile.ZipFile(zip_file_name, "w")

    try:
      sha1_hash = sha1()
      for data in large:
        sha1_hash.update(data)
        test_file.write(data)
      test_file.close()

      expected_stat = os.stat(test_file_name)
      expected_mode = 0o644
      expected_compress_type = extra_args.get("compress_type",
                                              zipfile.ZIP_STORED)
      time.sleep(5)  # Make sure the atime/mtime will change measurably.

      common.ZipWrite(zip_file, test_file_name, **extra_args)
      common.ZipWriteStr(zip_file, arcname_small, small, **extra_args)
      common.ZipClose(zip_file)

      # Verify the contents written by ZipWrite().
      self._verify(zip_file, zip_file_name, arcname_large,
                   sha1_hash.hexdigest(), test_file_name, expected_stat,
                   expected_mode, expected_compress_type)

      # Verify the contents written by ZipWriteStr().
      self._verify(zip_file, zip_file_name, arcname_small,
                   sha1(small).hexdigest(),
                   expected_compress_type=expected_compress_type)
    finally:
      os.remove(zip_file_name)
      os.remove(test_file_name)

  def _test_reset_ZIP64_LIMIT(self, func, *args):
    default_limit = (1 << 31) - 1
    self.assertEqual(default_limit, zipfile.ZIP64_LIMIT)
    func(*args)
    self.assertEqual(default_limit, zipfile.ZIP64_LIMIT)

  def test_ZipWrite(self):
    file_contents = os.urandom(1024)
    self._test_ZipWrite(file_contents)

  def test_ZipWrite_with_opts(self):
    file_contents = os.urandom(1024)
    self._test_ZipWrite(file_contents, {
        "arcname": "foobar",
        "perms": 0o777,
        "compress_type": zipfile.ZIP_DEFLATED,
    })
    self._test_ZipWrite(file_contents, {
        "arcname": "foobar",
        "perms": 0o700,
        "compress_type": zipfile.ZIP_STORED,
    })

  def test_ZipWrite_large_file(self):
    file_contents = get_2gb_string()
    self._test_ZipWrite(file_contents, {
        "compress_type": zipfile.ZIP_DEFLATED,
    })

  def test_ZipWrite_resets_ZIP64_LIMIT(self):
    self._test_reset_ZIP64_LIMIT(self._test_ZipWrite, "")

  def test_ZipWriteStr(self):
    random_string = os.urandom(1024)
    # Passing arcname
    self._test_ZipWriteStr("foo", random_string)

    # Passing zinfo
    zinfo = zipfile.ZipInfo(filename="foo")
    self._test_ZipWriteStr(zinfo, random_string)

    # Timestamp in the zinfo should be overwritten.
    zinfo.date_time = (2015, 3, 1, 15, 30, 0)
    self._test_ZipWriteStr(zinfo, random_string)

  def test_ZipWriteStr_with_opts(self):
    random_string = os.urandom(1024)
    # Passing arcname
    self._test_ZipWriteStr("foo", random_string, {
        "perms": 0o700,
        "compress_type": zipfile.ZIP_DEFLATED,
    })
    self._test_ZipWriteStr("bar", random_string, {
        "compress_type": zipfile.ZIP_STORED,
    })

    # Passing zinfo
    zinfo = zipfile.ZipInfo(filename="foo")
    self._test_ZipWriteStr(zinfo, random_string, {
        "compress_type": zipfile.ZIP_DEFLATED,
    })
    self._test_ZipWriteStr(zinfo, random_string, {
        "perms": 0o600,
        "compress_type": zipfile.ZIP_STORED,
    })

  def test_ZipWriteStr_large_file(self):
    # zipfile.writestr() doesn't work when the str size is over 2GiB even with
    # the workaround. We will only test the case of writing a string into a
    # large archive.
    long_string = get_2gb_string()
    short_string = os.urandom(1024)
    self._test_ZipWriteStr_large_file(long_string, short_string, {
        "compress_type": zipfile.ZIP_DEFLATED,
    })

  def test_ZipWriteStr_resets_ZIP64_LIMIT(self):
    self._test_reset_ZIP64_LIMIT(self._test_ZipWriteStr, "foo", "")
    zinfo = zipfile.ZipInfo(filename="foo")
    self._test_reset_ZIP64_LIMIT(self._test_ZipWriteStr, zinfo, "")

  def test_bug21309935(self):
    zip_file = tempfile.NamedTemporaryFile(delete=False)
    zip_file_name = zip_file.name
    zip_file.close()

    try:
      random_string = os.urandom(1024)
      zip_file = zipfile.ZipFile(zip_file_name, "w")
      # Default perms should be 0o644 when passing the filename.
      common.ZipWriteStr(zip_file, "foo", random_string)
      # Honor the specified perms.
      common.ZipWriteStr(zip_file, "bar", random_string, perms=0o755)
      # The perms in zinfo should be untouched.
      zinfo = zipfile.ZipInfo(filename="baz")
      zinfo.external_attr = 0o740 << 16
      common.ZipWriteStr(zip_file, zinfo, random_string)
      # Explicitly specified perms has the priority.
      zinfo = zipfile.ZipInfo(filename="qux")
      zinfo.external_attr = 0o700 << 16
      common.ZipWriteStr(zip_file, zinfo, random_string, perms=0o400)
      common.ZipClose(zip_file)

      self._verify(zip_file, zip_file_name, "foo",
                   sha1(random_string).hexdigest(),
                   expected_mode=0o644)
      self._verify(zip_file, zip_file_name, "bar",
                   sha1(random_string).hexdigest(),
                   expected_mode=0o755)
      self._verify(zip_file, zip_file_name, "baz",
                   sha1(random_string).hexdigest(),
                   expected_mode=0o740)
      self._verify(zip_file, zip_file_name, "qux",
                   sha1(random_string).hexdigest(),
                   expected_mode=0o400)
    finally:
      os.remove(zip_file_name)

class InstallRecoveryScriptFormatTest(unittest.TestCase):
  """Check the format of install-recovery.sh

  Its format should match between common.py and validate_target_files.py."""

  def setUp(self):
    self._tempdir = tempfile.mkdtemp()
    # Create a dummy dict that contains the fstab info for boot&recovery.
    self._info = {"fstab" : {}}
    dummy_fstab = \
        ["/dev/soc.0/by-name/boot /boot emmc defaults defaults",
         "/dev/soc.0/by-name/recovery /recovery emmc defaults defaults"]
    self._info["fstab"] = common.LoadRecoveryFSTab("\n".join, 2, dummy_fstab)
    # Construct the gzipped recovery.img and boot.img
    self.recovery_data = bytearray([
        0x1f, 0x8b, 0x08, 0x00, 0x81, 0x11, 0x02, 0x5a, 0x00, 0x03, 0x2b, 0x4a,
        0x4d, 0xce, 0x2f, 0x4b, 0x2d, 0xaa, 0x04, 0x00, 0xc9, 0x93, 0x43, 0xf3,
        0x08, 0x00, 0x00, 0x00
    ])
    # echo -n "boot" | gzip -f | hd
    self.boot_data = bytearray([
        0x1f, 0x8b, 0x08, 0x00, 0x8c, 0x12, 0x02, 0x5a, 0x00, 0x03, 0x4b, 0xca,
        0xcf, 0x2f, 0x01, 0x00, 0xc4, 0xae, 0xed, 0x46, 0x04, 0x00, 0x00, 0x00
    ])

  def _out_tmp_sink(self, name, data, prefix="SYSTEM"):
    loc = os.path.join(self._tempdir, prefix, name)
    if not os.path.exists(os.path.dirname(loc)):
      os.makedirs(os.path.dirname(loc))
    with open(loc, "w+") as f:
      f.write(data)

  def test_full_recovery(self):
    recovery_image = common.File("recovery.img", self.recovery_data)
    boot_image = common.File("boot.img", self.boot_data)
    self._info["full_recovery_image"] = "true"

    common.MakeRecoveryPatch(self._tempdir, self._out_tmp_sink,
                             recovery_image, boot_image, self._info)
    validate_target_files.ValidateInstallRecoveryScript(self._tempdir,
                                                        self._info)

  def test_recovery_from_boot(self):
    recovery_image = common.File("recovery.img", self.recovery_data)
    self._out_tmp_sink("recovery.img", recovery_image.data, "IMAGES")
    boot_image = common.File("boot.img", self.boot_data)
    self._out_tmp_sink("boot.img", boot_image.data, "IMAGES")

    common.MakeRecoveryPatch(self._tempdir, self._out_tmp_sink,
                             recovery_image, boot_image, self._info)
    validate_target_files.ValidateInstallRecoveryScript(self._tempdir,
                                                        self._info)
    # Validate 'recovery-from-boot' with bonus argument.
    self._out_tmp_sink("etc/recovery-resource.dat", "bonus", "SYSTEM")
    common.MakeRecoveryPatch(self._tempdir, self._out_tmp_sink,
                             recovery_image, boot_image, self._info)
    validate_target_files.ValidateInstallRecoveryScript(self._tempdir,
                                                        self._info)

  def tearDown(self):
    shutil.rmtree(self._tempdir)
