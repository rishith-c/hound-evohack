"""Portable export; requires build123d. Does not approve fabrication."""
from pathlib import Path
from build123d import export_step, export_stl
from rover import build, custom_parts

root=Path(__file__).parent
export_step(build(),root/'rover.step')
export_step(build(exploded=True),root/'rover_exploded.step')
(root/'parts').mkdir(exist_ok=True)
for name,shape in custom_parts().items():
    shape.label=name
    export_step(shape,root/'parts'/(name+'.step'))
    export_stl(shape,root/'parts'/(name+'.stl'))
print('Exported concept geometry. Physical validation remains outstanding.')
