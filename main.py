import asyncio
import json
import os
import re
from aiohttp import web
import httpx
from datetime import datetime, timezone, timedelta
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

# Alle API Keys aus Environment Variables (sicher!)
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY", "").strip()
MESHY_API_KEY = os.getenv("MESHY_API_KEY", "").strip()
FAL_API_KEY = os.getenv("FAL_API_KEY", "").strip()
KI_TELEGRAM_TOKEN = "8687941693:AAF204T_j8o_g6CA797uYBU9W2T8nXAo7ck"
TELEGRAM_CHAT_ID = "1668263126"
PORT = int(os.getenv("PORT", 8081))

CET = timezone(timedelta(hours=1))
KI_ORDERS_FILE = os.path.join(os.path.dirname(__file__), "ki_orders.json")


# === TELEGRAM ===

async def send_ki_telegram(text):
    if not KI_TELEGRAM_TOKEN:
        print("Kein Telegram Token - Nachricht uebersprungen")
        return
    url = f"https://api.telegram.org/bot{KI_TELEGRAM_TOKEN}/sendMessage"
    try:
        async with httpx.AsyncClient() as http:
            await http.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": text, "parse_mode": "HTML"})
    except Exception as e:
        print(f"KI Telegram Fehler: {e}")


# === CHATBOT ===

CHATBOT_SYSTEM_PROMPT = """Du bist der freundliche KI-Assistent von Viks 3Druckerei (viks3druckerei.de).
Du hilfst Kunden bei Fragen zu unseren 3D-Druck Produkten und Services.

WICHTIGE INFOS:
- Wir sind ein deutscher Online-Shop fuer personalisierte 3D-Druck Produkte
- Alle Produkte werden in Deutschland mit FDM 3D-Druckern aus PLA/PETG Filament hergestellt
- Jedes Stueck ist ein Unikat, individuell nach Kundenwunsch gefertigt

PRODUKTE:
- Namensaufsteller / Namensschilder (personalisiert mit Namen)
- LED Lampen mit individuellem Design
- Deko-Artikel (Vasen, Figuren, Halter)
- Schluesselanhaenger personalisiert
- Handyhalter / Tablet-Staender
- Stiftehalter / Organizer
- Individuelle Produkte nach Kundenwunsch (KI-Designer)

PREISE:
- Kleine Produkte: ab 9,99 EUR
- Mittlere Produkte: 14,99 - 29,99 EUR
- Grosse/Komplexe Produkte: 29,99 - 59,99 EUR
- Individuelle Anfragen: Preis nach Absprache

LIEFERUNG:
- Lieferzeit: 3-7 Werktage (da alles frisch gedruckt wird)
- Versand innerhalb Deutschlands: 4,99 EUR
- Ab 50 EUR versandkostenfrei
- Versand mit DHL

BESONDERHEITEN:
- KI-Designer: Kunden koennen eigene Produkte per KI designen lassen
- Individuelle Anfragen ueber die Seite "Individueller 3D-Druck"
- Verschiedene Farben verfuegbar
- Upload-Service: Kunden koennen eigene STL-Dateien hochladen

KONTAKT:
- Website: viks3druckerei.de
- Kontaktseite auf der Website

REGELN:
- Antworte immer auf Deutsch
- Sei freundlich und hilfsbereit
- Halte Antworten kurz (max 2-3 Saetze)
- Wenn du etwas nicht weisst, empfiehl dem Kunden die Kontaktseite
- Erwaehne bei passenden Fragen den KI-Designer
- Nutze keine Emojis"""

CHAT_HISTORY = {}


async def handle_chat(request):
    try:
        data = await request.json()
        message = data.get("message", "").strip()
        session_id = data.get("session_id", "default")
        if not message:
            return web.json_response({"error": "Nachricht fehlt"}, status=400)

        if session_id not in CHAT_HISTORY:
            CHAT_HISTORY[session_id] = []

        history = CHAT_HISTORY[session_id]
        history.append({"role": "user", "content": message})
        if len(history) > 20:
            history = history[-20:]
            CHAT_HISTORY[session_id] = history

        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-haiku-4-5-20251001",
                    "max_tokens": 300,
                    "system": CHATBOT_SYSTEM_PROMPT,
                    "messages": history,
                })

        if resp.status_code != 200:
            print(f"Chat API Fehler: {resp.status_code} {resp.text[:300]}")
            return web.json_response({"error": "KI antwortet nicht"}, status=500)

        reply = resp.json()["content"][0]["text"]
        history.append({"role": "assistant", "content": reply})
        return web.json_response({"ok": True, "reply": reply})

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# === ETSY TAGS ===

async def handle_etsy_tags(request):
    try:
        data = await request.json()
        product = data.get("product", "").strip()
        if not product:
            return web.json_response({"error": "Produkt fehlt"}, status=400)

        prompt = (
            f"Du bist ein Etsy SEO Experte. Erstelle fuer folgendes 3D-Druck Produkt von Viks 3Druckerei:\n"
            f"Produkt: {product}\n\n"
            f"Antworte NUR im JSON Format:\n"
            f'{{"title": "Optimierter Etsy Titel (max 140 Zeichen, wichtigste Keywords vorne, deutsch + englisch)", '
            f'"tags": ["tag1", "tag2", ... "tag13"] (genau 13 Tags, Mix aus deutsch und englisch, Long-Tail Keywords), '
            f'"description": "Etsy Beschreibung (erste 160 Zeichen SEO-optimiert, dann Details zu Material, Lieferzeit etc.)"}}'
        )

        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                "https://api.openai.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={"model": "gpt-4o-mini", "messages": [{"role": "user", "content": prompt}], "max_tokens": 800, "temperature": 0.7})

        if resp.status_code != 200:
            return web.json_response({"error": "KI nicht erreichbar"}, status=500)

        reply = resp.json()["choices"][0]["message"]["content"]
        json_match = re.search(r'\{.*\}', reply, re.DOTALL)
        if json_match:
            result = json.loads(json_match.group())
            return web.json_response(result)
        return web.json_response({"error": "KI Antwort ungueltig"}, status=500)

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# === 2D BILD GENERIERUNG (DALL-E) ===

async def handle_generate(request):
    try:
        data = await request.json()
        description = data.get("description", "")
        color = data.get("color", "")
        size = data.get("size", "mittel")
        if not description:
            return web.json_response({"error": "Beschreibung fehlt"}, status=400)

        prompt = (
            f"Realistic photograph of a 3D printed product: {description}. "
            f"Made from colored PLA plastic, visible subtle layer lines from FDM 3D printing. "
            f"{f'Color: {color}. ' if color else ''}"
            f"Size: approximately {size}. "
            f"Product photography on a clean white desk, natural daylight, "
            f"shot with professional camera. Modern product photo for an online shop. "
            f"NOT wood, NOT metal, NOT ceramic - only 3D printed plastic."
        )
        print(f"KI Designer: {description}")
        async with httpx.AsyncClient(timeout=120) as http:
            resp = await http.post(
                "https://api.openai.com/v1/images/generations",
                headers={"Authorization": f"Bearer {OPENAI_API_KEY}", "Content-Type": "application/json"},
                json={"model": "dall-e-3", "prompt": prompt, "n": 1, "size": "1024x1024", "quality": "standard"})
        if resp.status_code != 200:
            return web.json_response({"error": "Bildgenerierung fehlgeschlagen"}, status=500)
        image_url = resp.json()["data"][0]["url"]
        return web.json_response({"ok": True, "image_url": image_url})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# === 3D MODELL GENERIERUNG (MESHY) ===

async def handle_generate_3d(request):
    try:
        data = await request.json()
        description = data.get("description", "")
        if not description:
            return web.json_response({"error": "Beschreibung fehlt"}, status=400)

        prompt = f"3D printed product: {description}. Made from PLA plastic, smooth surface, product design, realistic"
        print(f"Meshy 3D: {description}")

        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                "https://api.meshy.ai/openapi/v2/text-to-3d",
                headers={"Authorization": f"Bearer {MESHY_API_KEY}", "Content-Type": "application/json"},
                json={"mode": "preview", "prompt": prompt, "art_style": "realistic"})

        if resp.status_code not in (200, 202):
            print(f"Meshy Fehler: {resp.status_code} {resp.text[:200]}")
            return web.json_response({"error": "3D-Generierung fehlgeschlagen"}, status=500)

        task_id = resp.json().get("result", "")
        print(f"Meshy Task gestartet: {task_id}")
        return web.json_response({"ok": True, "task_id": task_id})

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


async def handle_3d_status(request):
    try:
        task_id = request.match_info["task_id"]
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                f"https://api.meshy.ai/openapi/v2/text-to-3d/{task_id}",
                headers={"Authorization": f"Bearer {MESHY_API_KEY}"})

        if resp.status_code != 200:
            return web.json_response({"error": "Status-Abfrage fehlgeschlagen"}, status=500)

        data = resp.json()
        return web.json_response({
            "status": data.get("status", "UNKNOWN"),
            "progress": data.get("progress", 0),
            "model_url": data.get("model_urls", {}).get("glb", ""),
            "thumbnail": data.get("thumbnail_url", ""),
        })

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# === STL REFINE ===

async def refine_and_send_stl(preview_task_id, order):
    try:
        print(f"Refine gestartet fuer Bestellung #{order['id']} (Preview: {preview_task_id})")
        await send_ki_telegram(f"<b>STL-Generierung gestartet...</b>\nBestellung #{order['id']}\nDauert ca. 2-3 Minuten")

        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                "https://api.meshy.ai/openapi/v2/text-to-3d",
                headers={"Authorization": f"Bearer {MESHY_API_KEY}", "Content-Type": "application/json"},
                json={"mode": "refine", "preview_task_id": preview_task_id})

        if resp.status_code not in (200, 202):
            await send_ki_telegram(f"Refine Fehler: {resp.status_code}")
            return

        refine_task_id = resp.json().get("result", "")
        print(f"Refine Task: {refine_task_id}")

        for attempt in range(60):
            await asyncio.sleep(5)
            async with httpx.AsyncClient(timeout=15) as http:
                status_resp = await http.get(
                    f"https://api.meshy.ai/openapi/v2/text-to-3d/{refine_task_id}",
                    headers={"Authorization": f"Bearer {MESHY_API_KEY}"})

            if status_resp.status_code != 200:
                continue

            status_data = status_resp.json()
            if status_data.get("status") == "SUCCEEDED":
                model_urls = status_data.get("model_urls", {})
                stl_url = model_urls.get("stl", "")
                glb_url = model_urls.get("glb", "")
                obj_url = model_urls.get("obj", "")

                msg = f"<b>3D-Modell fertig!</b>\nBestellung #{order['id']}: {order['description']}\n\n"
                if stl_url:
                    msg += f"<b>STL:</b> {stl_url}\n"
                if glb_url:
                    msg += f"GLB: {glb_url}\n"
                if obj_url:
                    msg += f"OBJ: {obj_url}\n"

                await send_ki_telegram(msg)

                # STL als Datei per Telegram schicken
                if stl_url:
                    try:
                        async with httpx.AsyncClient(timeout=30) as dl_http:
                            stl_resp = await dl_http.get(stl_url)
                            if stl_resp.status_code == 200:
                                import tempfile
                                stl_path = os.path.join(tempfile.gettempdir(), f"bestellung_{order['id']}.stl")
                                with open(stl_path, "wb") as sf:
                                    sf.write(stl_resp.content)
                                # Datei per Telegram senden
                                tg_url = f"https://api.telegram.org/bot{KI_TELEGRAM_TOKEN}/sendDocument"
                                with open(stl_path, "rb") as sf:
                                    async with httpx.AsyncClient(timeout=30) as tg_http:
                                        await tg_http.post(tg_url,
                                            files={"document": (f"bestellung_{order['id']}.stl", sf)},
                                            data={"chat_id": TELEGRAM_CHAT_ID, "caption": f"STL Datei - {order['description']}"})
                                print(f"STL Datei gesendet fuer Bestellung #{order['id']}")
                    except Exception as e:
                        print(f"STL Download/Send Fehler: {e}")
                print(f"Refine fertig fuer Bestellung #{order['id']}")
                return

            if status_data.get("status") == "FAILED":
                await send_ki_telegram(f"Refine fehlgeschlagen fuer Bestellung #{order['id']}")
                return

        await send_ki_telegram(f"Refine Timeout fuer Bestellung #{order['id']}")

    except Exception as e:
        print(f"Refine Fehler: {e}")
        await send_ki_telegram(f"Refine Fehler: {e}")


# === BESTELLUNGEN ===

async def handle_order(request):
    try:
        data = await request.json()
        orders = []
        if os.path.exists(KI_ORDERS_FILE):
            with open(KI_ORDERS_FILE, "r") as f:
                orders = json.load(f)
        order = {
            "id": len(orders) + 1, "date": datetime.now(CET).isoformat(),
            "description": data.get("description", ""), "color": data.get("color", ""),
            "size": data.get("size", ""), "name": data.get("name", ""),
            "email": data.get("email", ""), "image_url": data.get("image_url", ""),
            "notes": data.get("notes", ""), "status": "neu"}
        orders.append(order)
        with open(KI_ORDERS_FILE, "w") as f:
            json.dump(orders, f, indent=2, ensure_ascii=False)

        model_link = data.get("model_url", "")
        task_id = data.get("task_id", "")
        if model_link:
            order["model_url"] = model_link

        await send_ki_telegram(
            f"<b>Neue KI-Designer Bestellung!</b>\n"
            f"Kunde: {order['name']}\nEmail: {order['email']}\n"
            f"Produkt: {order['description']}\nFarbe: {order['color']}\n"
            f"Groesse: {order['size']}\nNotizen: {order['notes']}\n"
            f"Bestellung #{order['id']}\n"
            f"STL wird generiert...")

        if task_id:
            asyncio.create_task(refine_and_send_stl(task_id, order))

        return web.json_response({"ok": True, "order_id": order["id"]})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# === MINI-ME: FOTO → 3D direkt (fal.ai Storage Upload + Meshy image-to-3d) ===

async def handle_minime_cartoon(request):
    try:
        reader = await request.multipart()
        field = await reader.next()
        if not field or field.name != "photo":
            return web.json_response({"error": "Foto fehlt"}, status=400)

        photo_data = await field.read()
        content_type = field.headers.get("Content-Type", "image/jpeg")

        if len(photo_data) > 30 * 1024 * 1024:
            return web.json_response({"error": "Foto zu gross (max 30 MB)"}, status=400)

        print(f"Mini-Me Foto empfangen ({len(photo_data)//1024} KB), lade zu fal.ai hoch...")

        # 1. Foto zu fal.ai Storage hochladen → öffentliche URL für Meshy
        ext = "jpg" if "jpeg" in content_type else content_type.split("/")[-1]
        async with httpx.AsyncClient(timeout=60) as http:
            upload_resp = await http.post(
                "https://rest.alpha.fal.ai/storage/upload",
                headers={"Authorization": f"Key {FAL_API_KEY}"},
                files={"file": (f"photo.{ext}", photo_data, content_type)},
            )

        if upload_resp.status_code != 200:
            print(f"fal.ai Upload Fehler: {upload_resp.status_code} {upload_resp.text[:200]}")
            return web.json_response({"error": "Foto-Upload fehlgeschlagen"}, status=500)

        image_url = upload_resp.json().get("url", "")
        if not image_url:
            return web.json_response({"error": "Foto-Upload fehlgeschlagen"}, status=500)
        print(f"Foto hochgeladen: {image_url[:60]}...")

        # 2. Meshy image-to-3d starten
        async with httpx.AsyncClient(timeout=30) as http:
            resp = await http.post(
                "https://api.meshy.ai/openapi/v1/image-to-3d",
                headers={"Authorization": f"Bearer {MESHY_API_KEY}", "Content-Type": "application/json"},
                json={"image_url": image_url, "ai_model": "meshy-4", "topology": "quad",
                      "target_polycount": 30000, "should_remesh": True},
            )

        if resp.status_code not in (200, 202):
            print(f"Meshy image-to-3d Fehler: {resp.status_code} {resp.text[:200]}")
            return web.json_response({"error": "3D-Generierung fehlgeschlagen"}, status=500)

        task_id = resp.json().get("result", "")
        print(f"Mini-Me 3D Task gestartet: {task_id}")
        return web.json_response({"ok": True, "task_id": task_id})

    except Exception as e:
        print(f"Mini-Me Fehler: {e}")
        return web.json_response({"error": str(e)}, status=500)


async def handle_minime_3d_status(request):
    try:
        task_id = request.match_info["task_id"]
        async with httpx.AsyncClient(timeout=15) as http:
            resp = await http.get(
                f"https://api.meshy.ai/openapi/v1/image-to-3d/{task_id}",
                headers={"Authorization": f"Bearer {MESHY_API_KEY}"},
            )

        if resp.status_code != 200:
            return web.json_response({"error": "Status-Abfrage fehlgeschlagen"}, status=500)

        data = resp.json()
        return web.json_response({
            "status": data.get("status", "UNKNOWN"),
            "progress": data.get("progress", 0),
            "model_url": data.get("model_urls", {}).get("glb", ""),
            "stl_url": data.get("model_urls", {}).get("stl", ""),
            "thumbnail": data.get("thumbnail_url", ""),
        })

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# === MINI-ME BESTELLUNG ===

async def handle_minime_order(request):
    try:
        data = await request.json()
        orders = []
        if os.path.exists(KI_ORDERS_FILE):
            with open(KI_ORDERS_FILE, "r") as f:
                orders = json.load(f)

        order = {
            "id": len(orders) + 1,
            "type": "mini-me",
            "date": datetime.now(CET).isoformat(),
            "name": data.get("name", ""),
            "email": data.get("email", ""),
            "size": data.get("size", ""),
            "cartoon_url": data.get("cartoon_url", ""),
            "model_url": data.get("model_url", ""),
            "stl_url": data.get("stl_url", ""),
            "notes": data.get("notes", ""),
            "status": "neu",
        }
        orders.append(order)
        with open(KI_ORDERS_FILE, "w") as f:
            json.dump(orders, f, indent=2, ensure_ascii=False)

        msg = (
            f"<b>Neue Mini-Me Bestellung!</b>\n"
            f"Kunde: {order['name']}\nEmail: {order['email']}\n"
            f"Groesse: {order['size']}\nNotizen: {order['notes']}\n"
            f"Bestellung #{order['id']}\n\n"
        )
        if order["stl_url"]:
            msg += f"<b>STL (drucken):</b> {order['stl_url']}\n"
        if order["model_url"]:
            msg += f"GLB (Vorschau): {order['model_url']}\n"
        if order["cartoon_url"]:
            msg += f"Cartoon: {order['cartoon_url']}\n"

        await send_ki_telegram(msg)

        # STL-Datei per Telegram schicken
        if order["stl_url"]:
            try:
                async with httpx.AsyncClient(timeout=30) as dl_http:
                    stl_resp = await dl_http.get(order["stl_url"])
                    if stl_resp.status_code == 200:
                        import tempfile
                        stl_path = os.path.join(tempfile.gettempdir(), f"minime_{order['id']}.stl")
                        with open(stl_path, "wb") as sf:
                            sf.write(stl_resp.content)
                        tg_url = f"https://api.telegram.org/bot{KI_TELEGRAM_TOKEN}/sendDocument"
                        with open(stl_path, "rb") as sf:
                            async with httpx.AsyncClient(timeout=30) as tg_http:
                                await tg_http.post(tg_url,
                                    files={"document": (f"minime_{order['id']}.stl", sf)},
                                    data={"chat_id": TELEGRAM_CHAT_ID,
                                          "caption": f"Mini-Me STL #{order['id']} – {order['name']}, {order['size']}"})
            except Exception as e:
                print(f"STL Send Fehler: {e}")

        return web.json_response({"ok": True, "order_id": order["id"]})

    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)


# === HEALTH CHECK ===

async def handle_health(request):
    return web.json_response({"status": "ok", "service": "ki-designer"})


# === CORS MIDDLEWARE ===

@web.middleware
async def cors_middleware(request, handler):
    if request.method == "OPTIONS":
        return web.Response(headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "Content-Type, ngrok-skip-browser-warning"})
    response = await handler(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


# === APP START ===

def main():
    app = web.Application(middlewares=[cors_middleware])
    app.router.add_get("/health", handle_health)
    app.router.add_post("/api/chat", handle_chat)
    app.router.add_post("/api/etsy-tags", handle_etsy_tags)
    app.router.add_post("/api/generate", handle_generate)
    app.router.add_post("/api/generate3d", handle_generate_3d)
    app.router.add_get("/api/3d-status/{task_id}", handle_3d_status)
    app.router.add_post("/api/order", handle_order)
    # Mini-Me
    app.router.add_post("/api/minime/cartoon", handle_minime_cartoon)
    app.router.add_get("/api/minime/3d-status/{task_id}", handle_minime_3d_status)
    app.router.add_post("/api/minime/order", handle_minime_order)

    print(f"KI-Designer API laeuft auf Port {PORT}")
    web.run_app(app, host="0.0.0.0", port=PORT)


if __name__ == "__main__":
    main()
