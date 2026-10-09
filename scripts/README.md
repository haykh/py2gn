# scripts/

Personal py2gn function files. Everything here except this README is gitignored and never packaged.

Files here are inside the checkout, so the project's `pyrefly.toml` / `ruff.toml` apply: with VS Code on this folder you get completion and full type checking from `import py2gn.lang as gn`.

Check a script without touching any .blend:

```powershell
.\check.ps1 scripts\my_funcs.py            # ruff + pyrefly
.\check.ps1 scripts\my_funcs.py -Compile   # ... and compile it in a background Blender
```

To use it live, point the py2gn panel's **Source File** at it and turn on **Recompile on Save**, or paste it into a text block and press **Compile Text**. Calls to node groups that only exist in your .blend fail under `-Compile` (factory settings); compile those in the real file.