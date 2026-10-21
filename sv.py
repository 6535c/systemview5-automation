"""Preserve Windows argument boundaries while dispatching CLI modes."""
import sys

if sys.version_info < (3,10):
    print('{"ok":false,"error":"Python 3.10 or newer is required"}')
    raise SystemExit(1)

if sys.argv[1:2] and sys.argv[1] in ['config','doctor','version']:
    from svsettings import main
elif sys.platform != 'win32':
    print('{"ok":false,"error":"A Windows desktop session is required"}')
    raise SystemExit(1)
elif sys.argv[1:2] == ['model']:
    del sys.argv[1]
    from svmodel import main
else:
    from svctl import main

if __name__ == '__main__':
    main()
