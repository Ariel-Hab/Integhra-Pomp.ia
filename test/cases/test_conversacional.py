# tests/cases/test_conversacional.py
from utils.models import TestCase, EntityExpectation

def get_tests():
    return [
        # Basic Conversation
        TestCase(name="Saludo", user_message="hola", expected_intent="saludo", category="conversacional"),
        TestCase(name="Despedida", user_message="chau nos vemos", expected_intent="despedida", category="conversacional"),
        TestCase(name="Afirmar", user_message="sí", expected_intent="afirmar", category="conversacional"),
        TestCase(name="Denegar", user_message="no gracias", expected_intent="denegar", category="conversacional"),
        TestCase(name="Agradecer", user_message="mil gracias", expected_intent="agradecer", category="conversacional"),
        TestCase(name="Pedir ayuda", user_message="como funciona?", expected_intent="pedir_ayuda", category="conversacional"),
        
        # Out of Scope / Edge Cases
        TestCase(name="Off Topic", user_message="qué hora es?", expected_intent="off_topic", category="conversacional"),
        TestCase(name="Out of Scope (general)", user_message="cómo se hace un risotto?", expected_intent="out_of_scope", category="conversacional"),
        TestCase(name="Consulta Profesional (Safety)", user_message="mi perro fue atropellado", expected_intent="consulta_veterinaria_profesional", category="conversacional"),
    ]