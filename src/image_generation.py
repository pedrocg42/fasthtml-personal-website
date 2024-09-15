import os
import uuid

import replicate as rplct
import requests
import uvicorn
from fastcore.parallel import threaded
from fasthtml.common import *
from PIL import Image
from pydantic import BaseModel
from sqlite_minutils.db import Database, Table

# Replicate setup (for generating images)
replicate_api_token = os.environ["REPLICATE_API_KEY"]
client = rplct.Client(api_token=replicate_api_token)


class Generation(BaseModel):
    id: str
    prompt: str
    folder: str


# gens database for storing generated image details
db: Database = database("data/gens.db")
if "gens" not in db.t:
    db.create_table(
        name="gens",
        columns={"prompt": str, "id": str, "folder": str},
        pk="id",
    )
gens: Table = db.t.gens


# Flexbox CSS (http://flexboxgrid.com/)
gridlink = Link(
    rel="stylesheet",
    href="https://cdnjs.cloudflare.com/ajax/libs/flexboxgrid/6.3.1/flexboxgrid.min.css",
    type="text/css",
)

# Our FastHTML app
app = FastHTML(hdrs=(picolink, gridlink))
rt = app.route


# Main page
@rt("/")
def get():
    inp = Input(id="new-prompt", name="prompt", placeholder="Enter a prompt")
    add = Form(
        Group(inp, Button("Generate")),
        hx_post="/",
        target_id="gen-list",
        hx_swap="afterbegin",
    )
    gen_containers = [generation_preview(Generation.model_validate(g)) for g in gens(limit=10)]  # Start with last 10
    gen_list = Div(
        *reversed(gen_containers),
        id="gen-list",
        cls="row",
    )  # flexbox container: class = row
    return Title("Image Generation Demo"), Main(
        H1("Magic Image Generation"),
        add,
        gen_list,
        cls="container",
    )


# Show the image (if available) and prompt for a generation
def generation_preview(g: Generation) -> Div:
    grid_cls = "box col-xs-12 col-sm-6 col-md-4 col-lg-3"
    image_path = f"{g.folder}/{g.id}.png"
    if os.path.exists(image_path):
        return Div(
            Card(
                Img(src=image_path, alt="Card image", cls="card-img-top"),
                Div(P(B("Prompt: "), g.prompt, cls="card-text"), cls="card-body"),
            ),
            id=f"gen-{g.id}",
            cls=grid_cls,
        )
    return Div(
        f"Generating gen {g.id} with prompt {g.prompt}",
        id=f"gen-{g.id}",
        hx_get=f"/gens/{g.id}",
        hx_trigger="every 2s",
        hx_swap="outerHTML",
        cls=grid_cls,
    )


# A pending preview keeps polling this route until we return the image preview
@rt("/gens/{id}")
def get(id: str) -> Div:
    return generation_preview(Generation.model_validate(gens.get(id)))


# For images, CSS, etc.
@rt("/{fname:path}.{ext:static}")
async def get(fname: str, ext: str):
    return FileResponse(f"{fname}.{ext}")


# Generation route
@rt("/")
def post(prompt: str):
    folder = "data/gens/"
    os.makedirs(folder, exist_ok=True)
    g = Generation(id=str(uuid.uuid4()), prompt=prompt, folder=folder)
    gens.insert(g)
    generate_and_save(g)
    clear_input = Input(
        id="new-prompt",
        name="prompt",
        placeholder="Enter a prompt",
        hx_swap_oob="true",
    )
    return generation_preview(g), clear_input


# Generate an image and save it to the folder (in a separate thread)
@threaded
def generate_and_save(g: Generation) -> bool:
    output = client.run(
        "black-forest-labs/flux-schnell",
        input={
            "aspect_ratio": "1:1",
            "prompt": g.prompt,
            "output_quality": 100,
            "disable_safety_checker": True,
        },
    )
    Image.open(requests.get(output[0], stream=True).raw).save(f"{g.folder}/{g.id}.png")
    return True


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", default="5001")))
