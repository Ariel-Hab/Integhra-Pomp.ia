import re
from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
import torch

class Paraphraser:
    def __init__(self, model_name="ramsrigouthamg/t5_paraphraser", max_length=128, token=None):
        self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        self.tokenizer = AutoTokenizer.from_pretrained(model_name, use_auth_token=token)
        self.model = AutoModelForSeq2SeqLM.from_pretrained(model_name, use_auth_token=token).to(self.device)
        self.max_length = max_length
        if torch.cuda.is_available():
            self.model = self.model.half()

    def proteger_entidades(self, texto, entidades):
        if entidades.get("nombre"):
            texto = re.sub(re.escape(entidades["nombre"]), "PROD", texto, flags=re.IGNORECASE)
        if entidades.get("proveedor"):
            texto = re.sub(re.escape(entidades["proveedor"]), "PROV", texto, flags=re.IGNORECASE)
        if entidades.get("cantidad"):
            texto = re.sub(re.escape(entidades["cantidad"]), "CANT", texto, flags=re.IGNORECASE)
        if entidades.get("dosis"):
            texto = re.sub(re.escape(entidades["dosis"]), "DOSIS", texto, flags=re.IGNORECASE)
        if entidades.get("compuesto"):
            texto = re.sub(re.escape(entidades["compuesto"]), "COMP", texto, flags=re.IGNORECASE)
        if entidades.get("categoria"):
            texto = re.sub(re.escape(entidades["categoria"]), "CAT", texto, flags=re.IGNORECASE)
        if entidades.get("dia"):
            texto = re.sub(re.escape(entidades["dia"]), "TIEMPO", texto, flags=re.IGNORECASE)
        if entidades.get("fecha"):
            texto = re.sub(re.escape(entidades["fecha"]), "FECHA", texto, flags=re.IGNORECASE)
        if entidades.get("cantidad_stock"):
            texto = re.sub(re.escape(entidades["cantidad_stock"]), "STOCK", texto, flags=re.IGNORECASE)
        if entidades.get("cantidad_descuento"):
            texto = re.sub(re.escape(entidades["cantidad_descuento"]), "DSCTO", texto, flags=re.IGNORECASE)
        return texto

    def restaurar_entidades(self, texto, entidades):
        if entidades.get("nombre"):
            texto = texto.replace("PROD", entidades["nombre"])
        if entidades.get("proveedor"):
            texto = texto.replace("PROV", entidades["proveedor"])
        if entidades.get("cantidad"):
            texto = texto.replace("CANT", entidades["cantidad"])
        if entidades.get("dosis"):
            texto = texto.replace("DOSIS", entidades["dosis"])
        if entidades.get("compuesto"):
            texto = texto.replace("COMP", entidades["compuesto"])
        if entidades.get("categoria"):
            texto = texto.replace("CAT", entidades["categoria"])
        if entidades.get("dia"):
            texto = texto.replace("TIEMPO", entidades["dia"])
        if entidades.get("fecha"):
            texto = texto.replace("FECHA", entidades["fecha"])
        if entidades.get("cantidad_stock"):
            texto = texto.replace("STOCK", entidades["cantidad_stock"])
        if entidades.get("cantidad_descuento"):
            texto = texto.replace("DSCTO", entidades["cantidad_descuento"])
        return texto

    def validar_entidades_protegidas(self, texto, etiquetas_esperadas=None):
        if etiquetas_esperadas is None:
            etiquetas_esperadas = ["PROD", "PROV", "CANT", "DOSIS", "COMP", "CAT", "TIEMPO", "FECHA", "STOCK", "DSCTO"]
        faltantes = [et for et in etiquetas_esperadas if et not in texto]
        return len(faltantes) == 0, faltantes

    def paraphrase(self, texto, entidades):
        texto_protegido = self.proteger_entidades(texto, entidades)
        input_text = f"paraphrase: {texto_protegido}"
        inputs = self.tokenizer(input_text, return_tensors="pt", max_length=self.max_length, truncation=True).to(self.device)
        outputs = self.model.generate(
            **inputs,
            max_length=self.max_length,
            num_beams=5,
            do_sample=True,
            top_k=50,
            top_p=0.95,
            num_return_sequences=1,
            early_stopping=True
        )
        texto_parafraseado = self.tokenizer.decode(outputs[0], skip_special_tokens=True).strip()
        ok, faltantes = self.validar_entidades_protegidas(texto_parafraseado)
        if not ok:
            print(f"⚠️ Se perdieron entidades protegidas: {faltantes}")
            return None
        texto_final = self.restaurar_entidades(texto_parafraseado, entidades)
        return texto_final

    def parafrasear(self, texto, **entidades):
        """
        Método que recibe texto y entidades (como argumentos clave=valor),
        y ejecuta todo el flujo completo: proteger, parafrasear, validar y restaurar.
        """
        return self.paraphrase(texto, entidades)

