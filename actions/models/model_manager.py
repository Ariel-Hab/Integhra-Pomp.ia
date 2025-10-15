# actions/models/model_manager.py - ✅ VERSIÓN CONSOLIDADA

import os
from groq import Groq
from dotenv import load_dotenv
import logging
from typing import Optional

# ✅ Import necesario para type hints
from rasa_sdk import Tracker

load_dotenv()
logger = logging.getLogger(__name__)

# ============== CONFIGURACIÓN ==============
SYSTEM_PROMPT = """Sos Pompi, asistente veterinario argentino.
Hablás en español rioplatense, usás "vos".
Respuestas MUY cortas: máximo 2 oraciones.
Siempre preguntás qué necesita el usuario."""
# ===========================================


class ChatModel:
    """Modelo Groq con inicialización lazy"""
    
    def __init__(self):
        self.client = None
        
    def load(self):
        """Carga el cliente Groq (solo primera vez)"""
        if self.client is not None:
            return
        
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            raise ValueError("❌ Falta GROQ_API_KEY en .env")
        
        self.client = Groq(api_key=api_key, timeout=30.0)
        logger.info("✅ Groq API inicializada")
    
    def generate(self, user_prompt: str, max_new_tokens: int = 100, 
                temperature: float = 0.7) -> Optional[str]:
        """
        Genera respuesta usando Groq
        
        Args:
            user_prompt: Prompt completo (puede incluir contexto)
            max_new_tokens: Límite de tokens
            temperature: Creatividad (0.0-1.0)
            
        Returns:
            Respuesta generada o None si falla
        """
        self.load()
        
        try:
            response = self.client.chat.completions.create(
                messages=[
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": user_prompt}
                ],
                model="llama-3.3-70b-versatile",
                temperature=temperature,
                max_tokens=max_new_tokens,
                top_p=0.9
            )
            
            result = response.choices[0].message.content.strip()
            return result if result else None
            
        except Exception as e:
            logger.error(f"❌ Error Groq: {e}")
            return None


# ============== INSTANCIA GLOBAL ==============
_chat_model = ChatModel()
# ==============================================


def generate_text(prompt: str, max_new_tokens: int = 100, 
                 temperature: float = 0.7) -> Optional[str]:
    """
    ✅ Genera respuesta SIN contexto (backward compatible)
    
    Args:
        prompt: Instrucción específica
        max_new_tokens: Límite de tokens
        temperature: Creatividad
        
    Returns:
        Respuesta generada o None si falla
    """
    return _chat_model.generate(prompt, max_new_tokens, temperature)


def generate_text_with_context(prompt: str, tracker: Optional[Tracker] = None, 
                               max_new_tokens: int = 100, 
                               temperature: float = 0.7) -> Optional[str]:
    """
    ✅ Genera respuesta CON contexto conversacional ligero
    
    Args:
        prompt: Instrucción específica
        tracker: Tracker de Rasa (opcional, para contexto)
        max_new_tokens: Límite de tokens
        temperature: Creatividad
        
    Returns:
        Respuesta generada o None si falla
    """
    try:
        # Construir contexto si hay tracker
        context_info = ""
        if tracker:
            context_info = _build_lightweight_context(tracker)
        
        # Combinar contexto + instrucción
        full_prompt = f"{context_info}\n\n{prompt}" if context_info else prompt
        
        return _chat_model.generate(full_prompt, max_new_tokens, temperature)
        
    except Exception as e:
        logger.error(f"[ModelManager] Error generando con contexto: {e}")
        return None


def _build_lightweight_context(tracker: Tracker) -> str:
    """
    ✅ Construye contexto conversacional mínimo (50-150 tokens aprox)
    
    Incluye:
    - Últimas 2-3 interacciones
    - Búsqueda activa
    - Sugerencia pendiente
    - Estado de engagement
    
    Args:
        tracker: Tracker de Rasa
        
    Returns:
        String con contexto formateado
    """
    try:
        context_parts = []
        
        # 1. ÚLTIMAS 2-3 INTERACCIONES (máximo 200 chars c/u)
        recent_events = []
        for event in reversed(list(tracker.events)):
            if event.get('event') == 'user':
                text = event.get('text', '')[:100]
                recent_events.insert(0, f"Usuario: {text}")
                if len(recent_events) >= 2:  # Solo últimas 2 del usuario
                    break
            elif event.get('event') == 'bot' and len(recent_events) > 0:
                text = event.get('text', '')[:100]
                recent_events.insert(0, f"Pompi: {text}")
                break
        
        if recent_events:
            context_parts.append("Conversación reciente:")
            context_parts.extend(recent_events[-3:])  # Máximo 3 mensajes
        
        # 2. BÚSQUEDA ACTIVA (si existe)
        search_history = tracker.get_slot('search_history')
        if search_history and len(search_history) > 0:
            last_search = search_history[-1]
            search_type = last_search.get('type', 'producto')
            params = last_search.get('parameters', {})
            
            # Resumir parámetros principales
            main_params = []
            for key in ['nombre', 'empresa', 'categoria', 'animal']:
                if key in params:
                    value = params[key]
                    if isinstance(value, dict):
                        value = value.get('value', value)
                    main_params.append(f"{key}={value}")
            
            if main_params:
                params_str = ', '.join(main_params[:2])  # Solo primeros 2
                context_parts.append(f"Búsqueda activa: {search_type} ({params_str})")
        
        # 3. SUGERENCIA PENDIENTE (crítico para off-topic)
        pending_suggestion = tracker.get_slot('pending_suggestion')
        if pending_suggestion:
            suggestion_type = pending_suggestion.get('suggestion_type', '')
            
            if suggestion_type == 'entity_correction':
                original = pending_suggestion.get('original_value', '')
                suggestions = pending_suggestion.get('suggestions', [])
                if suggestions:
                    context_parts.append(
                        f"Esperando confirmación: ¿'{original}' → '{suggestions[0]}'?"
                    )
            
            elif suggestion_type == 'type_correction':
                context_parts.append("Esperando confirmación de tipo de búsqueda")
            
            elif suggestion_type == 'missing_parameters':
                criteria = pending_suggestion.get('required_criteria', 'información')
                context_parts.append(f"Esperando que el usuario dé: {criteria}")
        
        # 4. INTENT ACTUAL (detectar off-topic)
        current_intent = tracker.latest_message.get('intent', {}).get('name', '')
        if current_intent:
            offtopic_intents = [
                'pedir_chiste', 'reirse', 'insultar', 'out_of_scope',
                'off_topic', 'consulta_veterinaria_profesional'
            ]
            
            if current_intent in offtopic_intents:
                context_parts.append(f"⚠️ Usuario cambió de tema ({current_intent})")
        
        # 5. ENGAGEMENT (modula el tono)
        engagement = tracker.get_slot('user_engagement_level')
        if engagement in ['frustrated', 'needs_help']:
            context_parts.append(f"⚠️ Usuario parece {engagement}")
        elif engagement == 'confused':
            context_parts.append(f"⚠️ Usuario está confundido")
        
        # Construir contexto final
        if context_parts:
            return "Contexto:\n" + "\n".join(context_parts)
        
        return ""
        
    except Exception as e:
        logger.error(f"[ModelManager] Error construyendo contexto: {e}")
        return ""


def get_model():
    """
    ✅ Por compatibilidad con código legacy
    Retorna (None, None) porque usamos API, no modelo local
    """
    _chat_model.load()
    return None, None