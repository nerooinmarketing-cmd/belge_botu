import base64
import json
import asyncio
import anthropic
from config import ANTHROPIC_API_KEY

client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)

PROMPTS = {
    "alis_fatura": """Sen bir Türk muhasebe belgesi analiz uzmanısın.
Görseldeki TÜM rakamları çok dikkatli oku. Rakamları kesinlikle karıştırma (3 ile 8, 1 ile 7, 0 ile 6 gibi).
Bu bir ALIŞ FATURASI. Aşağıdaki bilgileri JSON formatında çıkar:

{
  "belge_tipi": "Alış Faturası",
  "fatura_no": "...",
  "tarih": "GG.AA.YYYY",
  "saat": "SS:DD",
  "firma_adi": "...",
  "vergi_no": "...",
  "kalemler": [
    {
      "urun": "...",
      "birim": "...",
      "miktar": 0,
      "birim_fiyat": 0,
      "kdv_orani": 0,
      "kdv_tutari": 0,
      "kdv_li_toplam": 0
    }
  ],
  "kdvsiz_toplam": 0,
  "toplam_kdv": 0,
  "kdv_li_toplam": 0,
  "odeme_notu": "...",
  "notlar": "..."
}

Rakamları çift kontrol et: kdvsiz_toplam + toplam_kdv = kdv_li_toplam olmalı.
Eğer bir alanı okuyamazsan null döndür. Yorum yapma, sadece JSON döndür.""",

    "satis_fatura": """Sen bir Türk muhasebe belgesi analiz uzmanısın.
Görseldeki TÜM rakamları çok dikkatli oku. Rakamları kesinlikle karıştırma.
Bu bir SATIŞ FATURASI. Aşağıdaki bilgileri JSON formatında çıkar:

{
  "belge_tipi": "Satış Faturası",
  "fatura_no": "...",
  "tarih": "GG.AA.YYYY",
  "saat": "SS:DD",
  "firma_adi": "...",
  "vergi_no": "...",
  "kalemler": [
    {
      "urun": "...",
      "birim": "...",
      "miktar": 0,
      "birim_fiyat": 0,
      "kdv_orani": 0,
      "kdv_tutari": 0,
      "kdv_li_toplam": 0
    }
  ],
  "kdvsiz_toplam": 0,
  "toplam_kdv": 0,
  "kdv_li_toplam": 0,
  "odeme_notu": "...",
  "notlar": "..."
}

Rakamları çift kontrol et: kdvsiz_toplam + toplam_kdv = kdv_li_toplam olmalı.
Eğer bir alanı okuyamazsan null döndür. Yorum yapma, sadece JSON döndür.""",

    "alis_fis": """Sen bir Türk muhasebe belgesi analiz uzmanısın.
Görseldeki TÜM rakamları çok dikkatli oku. Rakamları kesinlikle karıştırma.
Bu bir ALIŞ FİŞİ. Aşağıdaki bilgileri JSON formatında çıkar:

{
  "belge_tipi": "Alış Fişi",
  "tarih": "GG.AA.YYYY",
  "saat": "SS:DD",
  "firma_adi": "...",
  "kalemler": [
    {
      "urun": "...",
      "kdv_orani": 0,
      "kdv_li_toplam": 0
    }
  ],
  "kdvsiz_toplam": 0,
  "toplam_kdv": 0,
  "kdv_li_toplam": 0,
  "odeme_notu": "...",
  "notlar": "..."
}

Rakamları çift kontrol et. Eğer bir alanı okuyamazsan null döndür. Yorum yapma, sadece JSON döndür.""",

    "satis_fis": """Sen bir Türk muhasebe belgesi analiz uzmanısın.
Görseldeki TÜM rakamları çok dikkatli oku. Rakamları kesinlikle karıştırma.
Bu bir SATIŞ FİŞİ. Aşağıdaki bilgileri JSON formatında çıkar:

{
  "belge_tipi": "Satış Fişi",
  "tarih": "GG.AA.YYYY",
  "saat": "SS:DD",
  "firma_adi": "...",
  "kalemler": [
    {
      "urun": "...",
      "kdv_orani": 0,
      "kdv_li_toplam": 0
    }
  ],
  "kdvsiz_toplam": 0,
  "toplam_kdv": 0,
  "kdv_li_toplam": 0,
  "odeme_notu": "...",
  "notlar": "..."
}

Rakamları çift kontrol et. Eğer bir alanı okuyamazsan null döndür. Yorum yapma, sadece JSON döndür.""",
}


async def analyze_document(image_path: str, doc_type: str = "alis_fis") -> dict:
    with open(image_path, "rb") as f:
        image_data = base64.standard_b64encode(f.read()).decode("utf-8")

    if image_path.lower().endswith(".png"):
        media_type = "image/png"
    elif image_path.lower().endswith(".webp"):
        media_type = "image/webp"
    else:
        media_type = "image/jpeg"

    prompt = PROMPTS.get(doc_type, PROMPTS["alis_fis"])

    for attempt in range(3):
        try:
            response = await client.messages.create(
                model="claude-haiku-4-5",
                max_tokens=2048,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_data,
                                },
                            },
                            {"type": "text", "text": prompt},
                        ],
                    }
                ],
            )

            raw = response.content[0].text.strip()
            if raw.startswith("```"):
                raw = raw.split("```")[1]
                if raw.startswith("json"):
                    raw = raw[4:]
            raw = raw.strip()
            return json.loads(raw)

        except json.JSONDecodeError:
            return {"belge_tipi": doc_type, "notlar": "OCR çıktısı ayrıştırılamadı, manuel kontrol gerekiyor."}
        except Exception as e:
            if attempt < 2:
                await asyncio.sleep(2 ** attempt)
                continue
            return {"belge_tipi": doc_type, "notlar": f"API hatası: {str(e)}"}
