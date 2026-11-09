# Configuration samples

Copies of configuration files the Materials libraries read. They are not
deployed from here; copy them to the location described below and edit them
there.

## material-library-rules.json

Says how sheet metal materials are recognised. Sheet metal materials can be
assigned only to sheet metal bodies, and sheet metal bodies can take only sheet
metal materials. Both settings are optional, but the file must have at least
one of them.

**`materialForms`**: sheet metal materials kept in the same library as the
other materials. A material property (`property`, default `AllowedFor`) lists
what the material may be used for, comma-separated: `SheetMetal`, `Solid`, or
`Solid, SheetMetal`. The value names can be changed with `solid` and
`sheetMetal`. Values match ignoring case and spaces, and values this version
does not know are ignored. A material without the property is for solids only.

A library holding at least one sheet metal material is offered twice in the
dialogs:
- `<library>` holds the materials allowed for solids. A sheet-metal-only
  material is hidden there.
- `<library>_SheetMetal` holds the materials allowed for sheet metal, and
  behaves as a sheet metal library always has (standards rows, filters, Sheet
  Metal Preferences). This is the only one offered in the NX Sheet Metal
  application.

A `Solid, SheetMetal` material is in both. The setting can be left out to
accept the defaults.

**`sheetMetalLibraries`**: lists whole library files that hold only sheet metal
materials (the older layout). Their materials need no property. These libraries
are offered as they are, with no `_SheetMetal` copy.

**Where it goes:** the material library folder, beside the library `.xml`
files. That is `%UGII_CUSTOMER_DIR%\MATERIALS` when it exists, otherwise
`%UGII_BASE_DIR%\MATERIALS`. To keep it somewhere else — for example because
the library folder is under Program Files — set
`BANXOPEN_MATERIAL_LIBRARY_RULES` to the file's full path.

**Names** are library ids: the `.xml` file name without its extension. They are
matched exactly, ignoring case.

**Without the file**, or without a `sheetMetalLibraries` list, a library file
counts as sheet metal when its name contains "sheetmetal", ignoring spaces and
case, and `materialForms` takes its defaults. A file that exists but is
invalid, has neither setting, or lists no libraries stops both dialogs from
starting rather than being ignored.
