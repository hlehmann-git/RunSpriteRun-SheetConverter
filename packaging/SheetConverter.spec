# PyInstaller recipe: builds dist/RunSpriteRunSheetConverter/ (the .exe plus its libraries). Run from the
# project folder:
#   pyinstaller --noconfirm packaging/SheetConverter.spec
import os

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

a = Analysis(
    [os.path.join(ROOT, "main.py")],
    pathex=[ROOT],
    excludes=["tkinter"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="RunSpriteRunSheetConverter",
    console=False,                       # a window app: no black terminal window
    upx=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="RunSpriteRunSheetConverter", upx=False)
