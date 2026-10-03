import unittest
from collections import namedtuple
from unittest.mock import patch

from scripts import doctor

Version = namedtuple("Version", "major minor micro")


class DoctorTests(unittest.TestCase):
    def test_wrong_python_version_fails(self):
        with (
            patch.object(doctor.sys, "version_info", Version(3, 12, 0)),
            patch.object(doctor, "version", return_value="available"),
        ):
            self.assertEqual(doctor.main(), 1)


if __name__ == "__main__":
    unittest.main()
