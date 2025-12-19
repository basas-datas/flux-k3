import runpod
import websocket
import uuid
import json
import base64
import logging
import urllib.request
import urllib.parse
import binascii

# ================== CONFIG ==================

COMFY_HTTP = "http://127.0.0.1:8188"
COMFY_WS = "ws://127.0.0.1:8188/ws"

# ================== LOGGING ==================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== COMFY HELPERS ==================

def upload_image(name: str, image_b64: str):
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


def load_image(img_info):
    params = urllib.parse.urlencode(img_info)
    with urllib.request.urlopen(f"{COMFY_HTTP}/view?{params}") as resp:
        return base64.b64encode(resp.read()).decode("utf-8")


def wait_and_get_history(ws, prompt_id):
    """
    Ждём полного завершения графа и возвращаем history
    """
    while True:
        msg = ws.recv()
        if isinstance(msg, str):
            data = json.loads(msg)
            if data.get("type") == "executing":
                if data["data"]["node"] is None and data["data"]["prompt_id"] == prompt_id:
                    break

    with urllib.request.urlopen(f"{COMFY_HTTP}/history/{prompt_id}") as resp:
        return json.loads(resp.read())[prompt_id]


# ================== FINAL IMAGE SELECTOR ==================

def extract_final_image(history: dict) -> str:
    """
    Строго возвращает ТОЛЬКО финальное изображение:
    приоритет:
      1. PreviewImage
      2. SaveImage
      3. VAEDecode
    """

    outputs = history.get("outputs", {})
    nodes = history.get("prompt", {})

    # 1️⃣ PreviewImage
    for node_id, node in nodes.items():
        if node.get("class_type") == "PreviewImage":
            images = outputs.get(node_id, {}).get("images", [])
            if images:
                logger.info(f"Returning PreviewImage from node {node_id}")
                return load_image(images[0])

    # 2️⃣ SaveImage
    for node_id, node in nodes.items():
        if node.get("class_type") == "SaveImage":
            images = outputs.get(node_id, {}).get("images", [])
            if images:
                logger.info(f"Returning SaveImage from node {node_id}")
                return load_image(images[0])

    # 3️⃣ VAEDecode (fallback)
    for node_id, node in nodes.items():
        if node.get("class_type") == "VAEDecode":
            images = outputs.get(node_id, {}).get("images", [])
            if images:
                logger.info(f"Returning VAEDecode output from node {node_id}")
                return load_image(images[0])

    raise RuntimeError("Final image not found in history")


# ================== HANDLER ==================

def handler(event):
    """
    Expected input:
    {
        "workflow": {...},
        "images": {
            "image.png": "base64..."
        }
    }
    """

    if "input" not in event or "workflow" not in event["input"]:
        return {"error": "Missing workflow in input"}

    workflow = event["input"]["workflow"]
    images = event["input"].get("images", {})

    # Upload input images
    for name, img_b64 in images.items():
        logger.info(f"Uploading image: {name}")
        upload_image(name, img_b64)

    # WebSocket
    client_id = str(uuid.uuid4())
    ws = websocket.WebSocket()
    ws.connect(f"{COMFY_WS}?clientId={client_id}")

    # Queue prompt
    result = queue_prompt(workflow, client_id)
    prompt_id = result["prompt_id"]
    logger.info(f"Prompt queued: {prompt_id}")

    # Wait & fetch history
    history = wait_and_get_history(ws, prompt_id)
    ws.close()

    try:
        final_image_b64 = extract_final_image(history)
    except Exception as e:
        logger.error(str(e))
        return {"error": "Failed to extract final image"}

    return {
        "image": final_image_b64
    }


# ================== START ==================

runpod.serverless.start({"handler": handler})
