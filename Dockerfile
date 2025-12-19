# Use specific version of nvidia cuda image
FROM wlsdml1114/multitalk-base:1.7 as runtime

# wget 설치 (URL 다운로드를 위해)
RUN apt-get update && apt-get install -y wget && rm -rf /var/lib/apt/lists/*

RUN pip install -U "huggingface_hub[hf_transfer]"
RUN pip install runpod websocket-client librosa

# Set working directory
WORKDIR /

RUN git clone https://github.com/comfyanonymous/ComfyUI.git && \
    cd ComfyUI && \
    pip install --no-cache-dir -r requirements.txt
RUN cd /ComfyUI/custom_nodes/ && \
    git clone https://github.com/ltdrdata/ComfyUI-Manager.git && \
    cd ComfyUI-Manager && \
    pip install --no-cache-dir -r requirements.txt

# Download models
RUN hf download Comfy-Org/flux1-kontext-dev_ComfyUI split_files/diffusion_models/flux1-dev-kontext_fp8_scaled.safetensors --local-dir /ComfyUI/models/unet/
RUN hf download comfyanonymous/flux_text_encoders clip_l.safetensors --local-dir=/ComfyUI/models/clip/
RUN hf download comfyanonymous/flux_text_encoders t5xxl_fp16.safetensors --local-dir=/ComfyUI/models/clip/
RUN wget -q https://huggingface.co/Comfy-Org/Lumina_Image_2.0_Repackaged/resolve/main/split_files/vae/ae.safetensors -O /ComfyUI/models/vae/ae.safetensors

# ----------------------------
# EXTRA: add missing assets (do not touch working ones)
# ----------------------------

# Ensure standard ComfyUI folders exist
RUN mkdir -p /ComfyUI/models/text_encoders /ComfyUI/models/diffusion_models /ComfyUI/models/loras

# Make your already-downloaded encoders visible in the standard folder (no duplicates)
RUN ln -sf /ComfyUI/models/clip/clip_l.safetensors /ComfyUI/models/text_encoders/clip_l.safetensors && \
    ln -sf /ComfyUI/models/clip/t5xxl_fp16.safetensors /ComfyUI/models/text_encoders/t5xxl_fp16.safetensors

# 1) t5xxl_fp8_e4m3fn_scaled.safetensors -> models/text_encoders
RUN hf download Comfy-Org/HiDream-I1_ComfyUI split_files/text_encoders/t5xxl_fp8_e4m3fn_scaled.safetensors --local-dir /ComfyUI/models/text_encoders/
# Source file exists here :contentReference[oaicite:1]{index=1}

# 2) LoRA: removal_timestep_alpha-2-1740.safetensors -> models/loras
RUN hf download lrzjason/ObjectRemovalFluxFill removal_timestep_alpha-2-1740.safetensors --local-dir /ComfyUI/models/loras/
# Source file exists here :contentReference[oaicite:2]{index=2}

# 3) diffusion_models: flux.1-fill-dev-OneReward-transformer_fp8.safetensors -> models/diffusion_models
RUN hf download Comfy-Org/OneReward_repackaged split_files/diffusion_models/flux.1-fill-dev-OneReward-transformer_fp8.safetensors --local-dir /ComfyUI/models/diffusion_models/
# Source file exists here :contentReference[oaicite:3]{index=3}

COPY . .
RUN chmod +x /entrypoint.sh

CMD ["/entrypoint.sh"]
