@ai_router.post("/assist_with")
async def ai_assist_with(body: AssistWithIn, request: Request, _=Depends(token_gate)):
    """
    Usa IA con un documento adjunto (subido o remoto) + prompt del usuario.
    - Si doc_url es http(s):// → descarga directa.
    - Si doc_url es /api/... → convierte a URL absoluta usando base_url.
    - Si es ruta local → intenta leerla (no recomendable en Render).
    - Si es imagen → usa GPT-4o visión.
    - Si es PDF/DOCX/TXT/MD → extrae texto.
    """
    doc_url = (body.doc_url or "").strip()
    if not doc_url:
        raise HTTPException(400, "doc_url vacío")

    filename = "doc.bin"
    raw = b""

    # 1) URL absoluta http(s)
    if _is_http(doc_url):
        filename, raw = await _download_http(doc_url)

    # 2) URL relativa: /api/upload/get/xxxx
    elif doc_url.startswith("/api/"):
        base = str(request.base_url).rstrip("/")  # ej: https://mediazion.eu
        full_url = base + doc_url                 # ej: https://mediazion.eu/api/upload/get/xxxx
        filename, raw = await _download_http(full_url)

    # 3) Ruta local (Render generalmente no lo usa)
    else:
        local = doc_url
        if local.startswith("/"):
            local = "." + local
        path = Path(local).resolve()
        if str(path).find(str(Path(".").resolve())) != 0:
            raise HTTPException(403, "Ruta no permitida")
        raw = _read_local(path)
        filename = path.name

    # 4) Determinar tipo de archivo
    ext = "." + filename.split(".")[-1].lower() if "." in filename else ".bin"

    # IMÁGENES → GPT-4o Vision
    if ext in IMAGE_EXTS:
        out = _vision_from_image_bytes(raw, body.prompt)
        return {"ok": True, "text": out}

    # DOCUMENTOS → extraer texto
    text = _extract_text_bytes(raw, ext)
    if not text.strip():
        raise HTTPException(400, "El documento no tiene texto legible")

    max_chars = body.max_chars or 120_000
    if len(text) > max_chars:
        text = text[:max_chars] + "\n\n[...texto recortado por longitud...]"

    # 5) Llamada a IA profesional con documento
    system = (
        "Eres el asistente profesional de MEDIAZION. Recibirás un documento textual y un encargo. "
        "Responde con rigor, bien estructurado y orientado a mediación (actas, resúmenes, borradores de acuerdos, comunicaciones). "
        "No inventes datos. Si algo no está en el documento, dilo claramente."
    )
    user_message = f"{body.prompt}\n\n=== DOCUMENTO INTEGRAL ===\n{text}"

    client = _client()
    try:
        resp = client.chat.completions.create(
            model=MODEL_ASSIST,
            messages=[
                {"role":"system","content": system},
                {"role":"user","content": user_message}
            ]
        )
        out = resp.choices[0].message.content
        return {"ok": True, "text": out}
    except Exception as ex:
        raise HTTPException(500, f"IA error: {ex}")
