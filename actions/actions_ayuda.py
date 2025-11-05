# actions/actions_ayuda.py

import logging
from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType

from actions.functions.chat_handler import generate_text_with_context


logger = logging.getLogger(__name__)

class ActionExplicarAyuda(Action):
    """Explica las capacidades del bot usando el LLM con fallback automático."""
    
    def name(self) -> str:
        return "action_explicar_ayuda"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list[EventType]:
        try:
            search_active = tracker.get_slot('search_active')
        except:
            search_active = None
        
        if search_active:
            logger.info("[ActionExplicarAyuda] Búsqueda activa detectada, generando ayuda contextual.")
            return self._ayuda_busqueda_activa(dispatcher, tracker)
        
        logger.info("[ActionExplicarAyuda] Sin búsqueda activa, generando ayuda general.")
        return self._ayuda_general(dispatcher, tracker)

    def _ayuda_general(self, dispatcher: CollectingDispatcher, tracker: Tracker) -> list[EventType]:
        prompt_general = """
        El usuario necesita ayuda. Generá una explicación muy amigable y corta sobre lo que podés hacer.
        Mencioná claramente que servís para dos cosas principales:
        1. Buscar **productos veterinarios** (por ejemplo, por nombre, animal o síntoma).
        2. Encontrar **ofertas** (por ejemplo, con descuento o 2x1).
        Terminá siempre con una pregunta simple como '¿Qué te gustaría buscar hoy?'.
        """
        
        # ✅ CORREGIDO: Ahora pasamos el dispatcher para que maneje fallback automáticamente
        logger.info("[ActionExplicarAyuda] Intentando generar respuesta de ayuda general...")
        response = generate_text_with_context(
            prompt=prompt_general,
            tracker=tracker,
            dispatcher=dispatcher,  # ✅ Pasamos dispatcher para fallback automático
            max_new_tokens=120,
            temperature=0.3
        )
        
        # ✅ CAMBIO CRÍTICO: Si response es None, el fallback YA fue enviado
        if response:
            # Solo enviar si hubo éxito en la generación
            dispatcher.utter_message(text=response)
            logger.info("[ActionExplicarAyuda] ✅ Respuesta generada enviada.")
        else:
            # No hacer nada - el fallback ya fue enviado por generate_text_with_context
            logger.info("[ActionExplicarAyuda] ✅ Fallback ya manejado por model_manager.")

        # Los botones se envían siempre
        dispatcher.utter_message(
            text="O elegí una de estas opciones:",
            buttons=[
                {"title": "Buscar productos", "payload": "/buscar_producto"},
                {"title": "Ver todas las ofertas", "payload": "/buscar_oferta"},
                {"title": "Ofertas con +10% desc", "payload": "/buscar_oferta{\"cantidad_descuento\": \"10\", \"comparador\": \"mas\"}"},
                {"title": "Productos para perros", "payload": "/buscar_producto{\"animal\": \"perro\"}"}
            ]
        )
        return []

    def _ayuda_busqueda_activa(self, dispatcher: CollectingDispatcher, tracker: Tracker) -> list[EventType]:
        # Extraemos los parámetros de forma segura
        current_params = tracker.get_slot('current_search_params') or {}
        last_search_type = tracker.get_slot('last_search_type') or 'producto'
        tipo_busqueda = "ofertas" if 'oferta' in str(last_search_type).lower() else "productos"
        
        if current_params:
            params_text = ", ".join([f"'{k}' es '{v}'" for k, v in current_params.items()])
            prompt_contextual = f"""
            El usuario está perdido durante una búsqueda. Ayudalo a continuar.
            Contexto actual: Está buscando **{tipo_busqueda}** con estos filtros: **{params_text}**.
            Explicále en tono amigable y simple qué puede hacer ahora. Sugerí que puede:
            - **Agregar** más filtros (ej: 'agregá para perros').
            - **Sacar** un filtro (ej: 'sacá el descuento').
            - **Cambiar** un filtro (ej: 'cambiá a gatos').
            Mantené la respuesta corta y directa.
            """
        else:
            prompt_contextual = f"""
            El usuario empezó a buscar **{tipo_busqueda}** pero no dijo qué filtros usar.
            Explicále amigablemente qué tipo de información puede darte.
            Si busca ofertas, sugerí filtros de descuento. Si busca productos, sugerí filtros por animal o síntoma.
            Dale un ejemplo simple.
            """

        # ✅ CORREGIDO: Pasar dispatcher para fallback automático
        logger.info("[ActionExplicarAyuda] Intentando generar respuesta de ayuda contextual...")
        response = generate_text_with_context(
            prompt=prompt_contextual,
            tracker=tracker,
            dispatcher=dispatcher,  # ✅ Pasamos dispatcher para fallback automático
            max_new_tokens=120,
            temperature=0.3
        )
        
        # ✅ CAMBIO CRÍTICO: Si response es None, el fallback YA fue enviado
        if response:
            dispatcher.utter_message(text=response)
            logger.info("[ActionExplicarAyuda] ✅ Respuesta contextual generada enviada.")
        else:
            # No hacer nada - el fallback ya fue enviado por generate_text_with_context
            logger.info("[ActionExplicarAyuda] ✅ Fallback contextual ya manejado por model_manager.")
        
        return []