# actions/models/chat_handler.py
"""
Módulo para gestión de generación de texto conversacional.
Maneja contexto, caché, fallbacks y comunicación con el dispatcher.
"""

import logging
import hashlib
import time
from typing import Optional, Dict, Any

from rasa_sdk import Tracker
from rasa_sdk.executor import CollectingDispatcher

from actions.models.model_manager import get_chat_model

logger = logging.getLogger(__name__)

# ============== CONFIGURACIÓN ==============
SYSTEM_PROMPT = """Te llamas Pompi, asistente veterinario.
Respuestas cortas: máximo 2 oraciones.
Siempre preguntá qué necesita."""

# Caché de respuestas
RESPONSE_CACHE = {}
MAX_CACHE_SIZE = 50

# Mensajes de fallback por tipo de error
FALLBACK_MESSAGES = {
    'timeout': "Estoy procesando tu consulta. ¿En qué más puedo ayudarte?",
    'connection_error': "Tengo un problema técnico temporal. ¿Podrías reformular tu pregunta?",
    'validation_error': "No pude generar una respuesta adecuada. ¿Podrías ser más específico?",
    'default': "¿En qué puedo ayudarte?"
}
# ===========================================


def generate_text_with_context(
    prompt: str, 
    tracker: Optional[Tracker] = None, 
    dispatcher: Optional[CollectingDispatcher] = None,
    fallback_template: Optional[str] = None,
    max_new_tokens: int = 150, 
    temperature: float = 0.3
) -> Optional[str]:
    """
    ✅ FUNCIÓN PRINCIPAL - GENERACIÓN DE TEXTO CON CONTEXTO
    
    Comportamiento:
    - Si hay dispatcher: SIEMPRE envía mensaje (éxito o fallback) y retorna None
    - Si NO hay dispatcher: retorna el texto generado o mensaje de fallback
    
    Args:
        prompt: Instrucción o pregunta para el modelo
        tracker: Tracker de Rasa para contexto (opcional)
        dispatcher: Dispatcher para enviar mensajes al usuario (opcional)
        fallback_template: Template de Rasa a usar si falla (opcional)
        max_new_tokens: Máximo de tokens a generar
        temperature: Temperatura para generación
    
    Returns:
        str si no hay dispatcher, None si hay dispatcher
    """
    start_time = time.time()
    
    try:
        # Obtener modelo (se inicializa automáticamente si es necesario)
        chat_model = get_chat_model()
        
        # Construir contexto
        context_info = _build_lightweight_context(tracker) if tracker else ""
        full_prompt = (
            f"Contexto de la conversación:\n{context_info}\n\nInstrucción:\n{prompt}"
            if context_info else prompt
        )
        
        # Verificar caché
        cache_key = _get_cache_key(full_prompt, max_new_tokens, temperature)
        if cache_key in RESPONSE_CACHE:
            logger.info("[ChatHandler] ✅ Respuesta desde caché")
            cached_response = RESPONSE_CACHE[cache_key]
            
            if dispatcher:
                dispatcher.utter_message(text=cached_response)
                return None
            return cached_response
        
        # Preparar mensajes
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_prompt}
        ]
        
        # Generar respuesta
        generated_text = chat_model.generate_raw(
            messages=messages,
            temperature=temperature,
            max_tokens=max_new_tokens
        )
        
        total_duration = time.time() - start_time

        # ✅ CASO 1: Generación exitosa
        if generated_text:
            logger.info(f"[ChatHandler] ✅ Generación exitosa en {total_duration:.2f}s")
            
            # Guardar en caché
            _update_cache(cache_key, generated_text)
            
            if dispatcher:
                dispatcher.utter_message(text=generated_text)
                logger.info("[ChatHandler] ✅ Mensaje enviado al usuario")
                return None
            
            return generated_text
        
        # ❌ CASO 2: Generación falló - usar fallback
        logger.warning(
            f"[ChatHandler] ⚠️ Generación falló después de {total_duration:.2f}s. "
            f"Usando fallback."
        )
        
        return _handle_fallback(dispatcher, fallback_template)
        
    except Exception as e:
        total_duration = time.time() - start_time
        logger.error(
            f"[ChatHandler] ❌ Error crítico después de {total_duration:.2f}s: {e}",
            exc_info=True
        )
        return _handle_fallback(dispatcher, fallback_template, emergency=True)


def generate_with_safe_fallback(
    prompt: str,
    dispatcher: CollectingDispatcher,
    tracker: Optional[Tracker] = None,
    fallback_template: str = "utter_default",
    max_new_tokens: int = 150,
    temperature: float = 0.1
) -> None:
    """
    ✅ WRAPPER SIMPLIFICADO - Genera con fallback seguro
    
    Usa generate_text_with_context con valores por defecto seguros.
    Ideal para usar directamente en actions.
    """
    generate_text_with_context(
        prompt=prompt,
        tracker=tracker,
        dispatcher=dispatcher,
        fallback_template=fallback_template,
        max_new_tokens=max_new_tokens,
        temperature=temperature
    )


# ============== FUNCIONES AUXILIARES ==============

def _get_cache_key(prompt: str, max_tokens: int, temperature: float) -> str:
    """Genera clave única para caché."""
    return hashlib.md5(
        f"{prompt}:{max_tokens}:{temperature}".encode('utf-8')
    ).hexdigest()


def _update_cache(key: str, value: str):
    """Actualiza caché con límite de tamaño."""
    if len(RESPONSE_CACHE) >= MAX_CACHE_SIZE:
        # Eliminar el primero (FIFO)
        RESPONSE_CACHE.pop(next(iter(RESPONSE_CACHE)))
    RESPONSE_CACHE[key] = value


def _handle_fallback(
    dispatcher: Optional[CollectingDispatcher],
    fallback_template: Optional[str] = None,
    emergency: bool = False
) -> Optional[str]:
    """
    Maneja fallback cuando la generación falla.
    
    Args:
        dispatcher: Dispatcher de Rasa
        fallback_template: Template a usar
        emergency: Si es True, usa mensaje de emergencia
    
    Returns:
        str si no hay dispatcher, None si hay dispatcher
    """
    # Determinar mensaje de fallback
    if emergency:
        fallback_text = FALLBACK_MESSAGES['default']
        log_source = "emergencia"
    else:
        fallback_text = FALLBACK_MESSAGES['connection_error']
        log_source = f"template '{fallback_template}'" if fallback_template else "texto fijo"
    
    logger.info(f"[ChatHandler] Fallback source: {log_source}")
    
    if dispatcher:
        # Intentar template primero
        if fallback_template and not emergency:
            try:
                dispatcher.utter_message(template=fallback_template)
                logger.info(f"[ChatHandler] ✅ Template enviado: {fallback_template}")
                return None
            except Exception as e:
                logger.error(f"[ChatHandler] ❌ Error con template: {e}")
        
        # Fallback a texto
        dispatcher.utter_message(text=fallback_text)
        logger.info(f"[ChatHandler] ✅ Fallback enviado: '{fallback_text}'")
        return None
    
    return fallback_text


def _build_lightweight_context(tracker: Tracker) -> str:
    """
    Construye contexto ligero desde el tracker.
    
    Extrae información relevante de:
    - Historial de búsquedas
    - Intent actual
    - Slots relevantes
    """
    try:
        context_parts = []
        
        # 1. Información de búsqueda reciente
        search_history = tracker.get_slot('search_history')
        if search_history and len(search_history) > 0:
            last_search = search_history[-1]
            params = last_search.get('parameters', {})
            if params:
                # Crear resumen de parámetros
                params_str = ", ".join([f"{k}='{v}'" for k, v in params.items()])
                context_parts.append(f"Última búsqueda: {params_str}")
        
        # 2. Intent actual
        intent_name = tracker.latest_message.get('intent', {}).get('name')
        if intent_name:
            context_parts.append(f"Intent actual: {intent_name}")
        
        # 3. Slots relevantes (opcional - agregar según necesidad)
        # user_name = tracker.get_slot('user_name')
        # if user_name:
        #     context_parts.append(f"Usuario: {user_name}")
        
        return "\n".join(context_parts) if context_parts else ""
        
    except Exception as e:
        logger.warning(f"[ChatHandler] Error construyendo contexto: {e}")
        return ""


# ============== UTILIDADES DE DIAGNÓSTICO ==============

def get_cache_stats() -> Dict[str, Any]:
    """Retorna estadísticas del caché de respuestas."""
    return {
        'total_entries': len(RESPONSE_CACHE),
        'max_size': MAX_CACHE_SIZE,
        'usage_percent': (len(RESPONSE_CACHE) / MAX_CACHE_SIZE) * 100
    }


def clear_cache():
    """Limpia el caché de respuestas."""
    global RESPONSE_CACHE
    cleared_count = len(RESPONSE_CACHE)
    RESPONSE_CACHE.clear()
    logger.info(f"[ChatHandler] Caché limpiado ({cleared_count} entradas)")
    return cleared_count