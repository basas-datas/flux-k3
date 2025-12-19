import runpod
import websocket
import uuid
import json
import os
import base64
import logging
import urllib.request
import urllib.parse
import binascii
import time

# ================== CONFIG ==================

COMFY_HTTP = "http://127.0.0.1:8188"
COMFY_WS = "ws://127.0.0.1:8188/ws"

# ================== LOGGING ==================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== COMFY HELPERS ==================

def upload_image(name: str, image_b64: str):
    """Upload image to ComfyUI"""
    try:
        image_bytes = base64.b64decode(image_b64)
    except binascii.Error:
        raise ValueError("Invalid base64 image")

    boundary = uuid.uuid4().hex
    data = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{name}"\r\n'
        f"Content-Type: application/octet-stream\r\n\r\n"
    ).encode() + image_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        f"{COMFY_HTTP}/upload/image",
        data=data,
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
        method="POST",
    )

    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def queue_prompt(prompt: dict, client_id: str):
    payload = {
        "prompt": prompt,
        "client_id": client_id,
    }
    req = urllib.request.Request(
        f"{COMFY_HTTP}/prompt",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read())


def get_images(ws, prompt_id):
    # ждём КОНЕЦ ГРАФА
    while True:
        msg = ws.recv()
        if isinstance(msg, str):
            data = json.loads(msg)
            if data.get("type") == "executing":
                if data["data"]["node"] is None and data["data"]["prompt_id"] == prompt_id:
                    break

    # теперь history гарантированно готов
    with urllib.request.urlopen(f"{COMFY_HTTP}/history/{prompt_id}") as resp:
        history = json.loads(resp.read())[prompt_id]

    images = {}
    for node_id, node_data in history["outputs"].items():
        if "images" in node_data:
            images[node_id] = []
            for img in node_data["images"]:
                images[node_id].append(load_image(img))

    return images



def load_image(img_info):
    params = urllib.parse.urlencode(img_info)
    with urllib.request.urlopen(f"{COMFY_HTTP}/view?{params}") as resp:
        return base64.b64encode(resp.read()).decode("utf-8")

# ================== HANDLER ==================

def handler(event):
    """
    Expected input:
    {
        "workflow": {...},        # full ComfyUI graph
        "images": {
            "image.png": "base64..."
        }
    }
    """

    try:
        workflow = event["input"]["workflow"]
    except KeyError:
        return {"error": "Missing 'workflow' in input"}

    images = event["input"].get("images", {})

    # Upload images
    for name, img_b64 in images.items():
        logger.info(f"Uploading image: {name}")
        upload_image(name, img_b64)

    # WebSocket session
    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")

    # Send workflow
    result = queue_prompt(workflow, client_id)
    prompt_id = result["prompt_id"]

    logger.info(f"Prompt queued: {prompt_id}")

    images_out = get_images(ws, prompt_id)
    ws.close()

    if not images_out:
        return {"error": "No images generated"}

    # Return FIRST image (standard for RunPod)
    for node_id in images_out:
        if images_out[node_id]:
            return {
                "image": images_out[node_id][0],
                "node_id": node_id,
            }

    return {"error": "Images not found"}

# ================== START ==================

runpod.serverless.start({"handler": handler})
