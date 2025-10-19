# tests/utils/bot_client.py

import requests
from typing import Optional, Dict

class Config:
    """Centraliza la configuración para los tests del bot."""
    BOT_URL = "http://localhost:8000"
    PARSE_ENDPOINT = f"{BOT_URL}/model/parse"
    MESSAGE_ENDPOINT = f"{BOT_URL}/message"
    RESET_ENDPOINT = f"{BOT_URL}/reset_context"
    HEALTH_ENDPOINT = f"{BOT_URL}/health"
    TRACKER_ENDPOINT = f"{BOT_URL}/tracker" # Base URL for tracker
    USER_ID = "test_user_123"
    TIMEOUT = 10
    RESET_BETWEEN_TESTS = True
    
    # Colores ANSI para una salida más clara en la consola
    class Colors:
        HEADER = '\033[95m'
        OKBLUE = '\033[94m'
        OKCYAN = '\033[96m'
        OKGREEN = '\033[92m'
        WARNING = '\033[93m'
        FAIL = '\033[91m'
        ENDC = '\033[0m'
        BOLD = '\033[1m'
        UNDERLINE = '\033[4m'

class BotClient:
    """Cliente HTTP para interactuar con el servidor del bot de Rasa."""
    
    def __init__(self, config: Config):
        self.config = config
    
    def check_health(self) -> bool:
        """Verifica que el bot esté disponible y responda correctamente."""
        try:
            response = requests.get(self.config.HEALTH_ENDPOINT, timeout=5)
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            print(f"{self.config.Colors.FAIL}❌ Bot no disponible: {e}{self.config.Colors.ENDC}")
            return False
    
    def reset_context(self) -> bool:
        """Envía una solicitud para reiniciar el contexto del usuario de prueba."""
        try:
            response = requests.post(
                self.config.RESET_ENDPOINT,
                params={"user_id": self.config.USER_ID},
                timeout=5
            )
            return response.status_code == 200
        except requests.exceptions.RequestException as e:
            print(f"{self.config.Colors.WARNING}⚠️  No se pudo resetear el contexto: {e}{self.config.Colors.ENDC}")
            return False
    
    def send_message(self, message: str) -> Optional[Dict]:
        """Envía un mensaje al bot y retorna la respuesta JSON completa."""
        payload = {
            "message": message,
            "user_id": self.config.USER_ID
        }
        try:
            response = requests.post(
                self.config.MESSAGE_ENDPOINT,
                json=payload,
                timeout=self.config.TIMEOUT
            )
            
            if response.status_code != 200:
                print(f"{self.config.Colors.FAIL}HTTP Error: {response.status_code} - {response.text}{self.config.Colors.ENDC}")
                return None
            
            return response.json()
            
        except requests.exceptions.Timeout:
            print(f"{self.config.Colors.FAIL}⏱️  Timeout esperando respuesta del bot.{self.config.Colors.ENDC}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"{self.config.Colors.FAIL}Error enviando mensaje: {e}{self.config.Colors.ENDC}")
            return None
    def parse_message(self, message: str) -> Optional[Dict]:
        """Envía un mensaje al endpoint de NLU y retorna el análisis."""
        payload = {
            "text": message
        }
        try:
            response = requests.post(
                self.config.PARSE_ENDPOINT,
                json=payload,
                timeout=self.config.TIMEOUT
            )
            
            if response.status_code != 200:
                print(f"{self.config.Colors.FAIL}HTTP Error: {response.status_code} - {response.text}{self.config.Colors.ENDC}")
                return None
            
            # El endpoint /model/parse devuelve directamente el JSON que necesitamos
            return response.json()
            
        except requests.exceptions.Timeout:
            print(f"{self.config.Colors.FAIL}⏱️  Timeout esperando respuesta del bot.{self.config.Colors.ENDC}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"{self.config.Colors.FAIL}Error enviando mensaje para parse: {e}{self.config.Colors.ENDC}")
            return None
    def get_tracker(self) -> Optional[Dict]:
        """Obtiene el tracker actual del usuario de prueba."""
        url = f"{self.config.TRACKER_ENDPOINT}/{self.config.USER_ID}"
        try:
            response = requests.get(url, timeout=5)
            if response.status_code == 200:
                return response.json()
            return None
        except requests.exceptions.RequestException:
            return None