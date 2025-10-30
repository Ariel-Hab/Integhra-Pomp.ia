# actions/api_client.py
import requests
import logging
import time
from typing import Dict, Any, Tuple

logger = logging.getLogger(__name__)

# URLs de tu API
BASE_URL = "http://integhra-dev.ddns.net:8000/api/integhra/v1"
PRODUCT_SEARCH_URL = f"{BASE_URL}/ProductSearchPomp/"
OFFER_SEARCH_URL = f"{BASE_URL}/OfferSearchPomp/"

# Credenciales
API_HEADERS = {
    "Authorization": "token 06eff8839ae94dbbccd18e0f5fa50392c20febb1",
    "Content-Type": "application/json"
}

def search_products(api_params: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
    """
    Busca productos en la API.
    
    Backend devuelve:
    {
        "error": bool,
        "data": [...],              ← Lista de productos
        "total_results": int,
        "returned_results": int,
        "message": str
    }
    """
    logger.info(f"📞 [APIClient] Llamando a ProductSearch")
    logger.debug(f"    Params enviados: {api_params}")
    
    api_start = time.time()
    try:
        response = requests.get(
            PRODUCT_SEARCH_URL,
            params=api_params,
            headers=API_HEADERS,
            timeout=30
        )
        api_time = time.time() - api_start
        
        logger.info(f"📥 [APIClient] Status Code: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        # Log de la estructura recibida (útil para debug)
        logger.debug(f"    Claves en respuesta: {list(data.keys())}")
        
        # ✅ PRODUCTOS: Backend devuelve 'data'
        normalized_data = {
            "total_results": data.get('total_results', 0),
            "results": data.get('data', []),  # ✅ Correcto para productos
            "error": data.get('error', False),
            "message": data.get('message', ''),
            "returned_results": data.get('returned_results', 0),
            "search_criteria": data.get('search_criteria', {})
        }
        
        logger.info(f"✅ [APIClient] Productos OK ({api_time:.2f}s)")
        logger.info(f"    Total: {normalized_data['total_results']}")
        logger.info(f"    Devueltos: {len(normalized_data['results'])}")
        
        return normalized_data, api_time

    except requests.exceptions.HTTPError as e:
        api_time = time.time() - api_start
        
        # Intentar extraer mensaje de error del backend
        try:
            error_detail = e.response.json()
            error_msg = error_detail.get('message', str(e))
        except:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        
        logger.error(f"❌ [APIClient] {error_msg} ({api_time:.2f}s)")
        
        return {
            "total_results": 0,
            "results": [],
            "error": True,
            "message": error_msg
        }, api_time
        
    except requests.exceptions.RequestException as e:
        api_time = time.time() - api_start
        error_msg = f"Error en API (Productos): {str(e)}"
        logger.error(f"❌ [APIClient] {error_msg} ({api_time:.2f}s)")
        
        return {
            "total_results": 0,
            "results": [],
            "error": True,
            "message": error_msg
        }, api_time


def search_offers(api_params: Dict[str, Any]) -> Tuple[Dict[str, Any], float]:
    """
    Busca ofertas en la API.
    
    Backend devuelve:
    {
        "error": bool,
        "offers": [...],            ← Lista de ofertas (diferente nombre!)
        "total_results": int,
        "returned_results": int,
        "message": str
    }
    """
    logger.info(f"📞 [APIClient] Llamando a OfferSearch")
    logger.debug(f"    Params enviados: {api_params}")
    
    api_start = time.time()
    try:
        response = requests.get(
            OFFER_SEARCH_URL,
            params=api_params,
            headers=API_HEADERS,
            timeout=30
        )
        api_time = time.time() - api_start
        
        logger.info(f"📥 [APIClient] Status Code: {response.status_code}")
        
        response.raise_for_status()
        data = response.json()
        
        logger.debug(f"    Claves en respuesta: {list(data.keys())}")
        
        # ✅ OFERTAS: Backend devuelve 'offers' (no 'data')
        normalized_data = {
            "total_results": data.get('total_results', 0),
            "results": data.get('offers', []),  # ✅ Cambiar 'data' por 'offers'
            "error": data.get('error', False),
            "message": data.get('message', ''),
            "returned_results": data.get('returned_results', 0),
            "search_criteria": data.get('search_criteria', {}),
            "debug_info": data.get('debug_info', {})
        }
        
        logger.info(f"✅ [APIClient] Ofertas OK ({api_time:.2f}s)")
        logger.info(f"    Total: {normalized_data['total_results']}")
        logger.info(f"    Devueltos: {len(normalized_data['results'])}")
        
        return normalized_data, api_time
        
    except requests.exceptions.HTTPError as e:
        api_time = time.time() - api_start
        
        try:
            error_detail = e.response.json()
            error_msg = error_detail.get('message', str(e))
        except:
            error_msg = f"HTTP {e.response.status_code}: {e.response.text[:200]}"
        
        logger.error(f"❌ [APIClient] {error_msg} ({api_time:.2f}s)")
        
        return {
            "total_results": 0,
            "results": [],
            "error": True,
            "message": error_msg
        }, api_time
        
    except requests.exceptions.RequestException as e:
        api_time = time.time() - api_start
        error_msg = f"Error en API (Ofertas): {str(e)}"
        logger.error(f"❌ [APIClient] {error_msg} ({api_time:.2f}s)")
        
        return {
            "total_results": 0,
            "results": [],
            "error": True,
            "message": error_msg
        }, api_time
