# actions/actions_ayuda.py

from rasa_sdk import Action, Tracker
from rasa_sdk.executor import CollectingDispatcher
from rasa_sdk.events import EventType
import logging

logger = logging.getLogger(__name__)

class ActionExplicarAyuda(Action):
    """Explica las capacidades del bot - maneja contexto automáticamente"""
    
    def name(self) -> str:
        return "action_explicar_ayuda"
    
    def run(self, dispatcher: CollectingDispatcher, tracker: Tracker, domain: dict) -> list[EventType]:
        """Detecta automáticamente si hay búsqueda activa y responde apropiadamente"""
        
        # Detectar si hay búsqueda activa
        search_active = tracker.get_slot('search_active')
        current_params = tracker.get_slot('current_search_params') or {}
        last_search_type = tracker.get_slot('last_search_type') or 'producto'
        
        # Si hay búsqueda activa, dar ayuda contextual
        if search_active:
            logger.info("[ActionExplicarAyuda] Búsqueda activa detectada, dando ayuda contextual")
            return self._ayuda_busqueda_activa(dispatcher, current_params, last_search_type)
        
        # Si no hay búsqueda activa, dar ayuda general
        logger.info("[ActionExplicarAyuda] Sin búsqueda activa, dando ayuda general")
        return self._ayuda_general(dispatcher)
    
    def _ayuda_general(self, dispatcher: CollectingDispatcher) -> list[EventType]:
        """Ayuda general cuando NO hay búsqueda activa"""
        
        mensaje_ayuda = """¡Te ayudo a buscar productos veterinarios y ofertas!

**Podés buscar PRODUCTOS por:**
- Nombre (ej: "busco ivermectina")
- Animal (ej: "algo para perros")
- Síntoma (ej: "para pulgas")
- Empresa (ej: "productos de Holliday")
- Categoría (ej: "antiparasitarios")

**Podés buscar OFERTAS por:**
- Descuento mínimo (ej: "ofertas con más de 10%")
- Bonificación (ej: "ofertas 2x1")
- Producto específico (ej: "ofertas de ivermectina")
- Empresa (ej: "ofertas de Biogénesis")

**Ejemplos completos:**
- "Busco antiparasitarios para gatos"
- "Ofertas con más de 15% de descuento"
- "Alimento para perros en oferta"

¿Qué estás buscando hoy?"""
        
        dispatcher.utter_message(text=mensaje_ayuda)
        
        dispatcher.utter_message(
            text="O elegí una opción:",
            buttons=[
                {"title": "Buscar productos", "payload": "/buscar_producto"},
                {"title": "Ver todas las ofertas", "payload": "/buscar_oferta"},
                {"title": "Ofertas con +10% desc", "payload": "/buscar_oferta{\"cantidad_descuento\": \"10\", \"comparador\": \"mas\"}"},
                {"title": "Productos para perros", "payload": "/buscar_producto{\"animal\": \"perro\"}"}
            ]
        )
        
        return []
    
    def _ayuda_busqueda_activa(self, dispatcher: CollectingDispatcher, 
                                current_params: dict, last_search_type: str) -> list[EventType]:
        """Ayuda contextual cuando SÍ hay búsqueda activa"""
        
        # Determinar tipo de búsqueda
        is_oferta = 'oferta' in str(last_search_type).lower()
        tipo_busqueda = "ofertas" if is_oferta else "productos"
        
        if current_params:
            params_text = ", ".join([f"{k}: {v}" for k, v in current_params.items()])
            
            if is_oferta:
                mensaje = f"""Actualmente estás buscando **ofertas** con: {params_text}

**Podés modificar tu búsqueda de ofertas:**
- "Agregá más de 20% de descuento"
- "Cambiá a ofertas 2x1"
- "Solo ofertas de Holliday"
- "Ofertas para gatos"
- "Sacá el descuento"

**O agregar más detalles:**
- Producto específico en oferta
- Empresa/marca
- Animal o categoría"""
            else:
                mensaje = f"""Actualmente estás buscando **productos** con: {params_text}

**Podés modificar tu búsqueda:**
- "Agregá ivermectina"
- "Cambiá a gatos"
- "Solo de Biogénesis"
- "Sacá el síntoma"
- "Mostrá ofertas"

**O agregar más detalles:**
- Nombre exacto del producto
- Síntoma específico
- Empresa/marca preferida"""
        else:
            if is_oferta:
                mensaje = f"""Estás buscando **ofertas** pero todavía no especificaste filtros.

**Podés decirme:**
- "Con más de 10% de descuento"
- "Ofertas 2x1"
- "De ivermectina"
- "Para perros"
- "De Holliday"

**Ejemplos:**
- "Ofertas con más de 15%"
- "Ofertas 2x1 de antiparasitarios"
- "Ofertas de alimento para gatos"
"""
            else:
                mensaje = f"""Estás buscando **productos** pero todavía no especificaste filtros.

**Podés decirme:**
- Nombre del producto que buscás
- Para qué animal es
- Qué síntoma querés tratar
- Qué empresa preferís
- O si querés ver ofertas"""
        
        dispatcher.utter_message(text=mensaje)
        
        # Botones contextuales
        if is_oferta:
            buttons = [
                {"title": "Modificar filtros", "payload": "/modificar_busqueda"},
                {"title": "Ver todas las ofertas", "payload": "/buscar_oferta"},
                {"title": "Buscar productos", "payload": "/buscar_producto"},
                {"title": "Cancelar", "payload": "/denegar"}
            ]
        else:
            buttons = [
                {"title": "Modificar búsqueda", "payload": "/modificar_busqueda"},
                {"title": "Ver ofertas", "payload": "/buscar_oferta"},
                {"title": "Nueva búsqueda", "payload": "/buscar_producto"},
                {"title": "Cancelar", "payload": "/denegar"}
            ]
        
        dispatcher.utter_message(text="¿Qué querés hacer?", buttons=buttons)
        
        return []