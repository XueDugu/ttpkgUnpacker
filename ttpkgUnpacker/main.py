import os
import sys

if __package__ in (None, ""):
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ttpkgUnpacker.controller.main import Main


def main(argv=None):
    return Main(argv or sys.argv).run()


if __name__ == "__main__":
    raise SystemExit(main())
