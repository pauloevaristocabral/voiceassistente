import speech_recognition as sr
from gtts import gTTS
import os
import io
import pygame
import numpy as np
import time
import tkinter as tk
import cv2
import requests
from threading import Thread
from PIL import Image, ImageTk

# Criando a interface gráfica
root = tk.Tk()
root.title("Assistente Virtual")
root.geometry("600x600")

# Carregar vídeo
video_path = "wave.mp4"
cap = cv2.VideoCapture(video_path)
video_label = tk.Label(root)
video_label.pack()

def play_video():
    """Executa o vídeo continuamente sem parar."""
    while True:
        ret, frame = cap.read()
        if not ret:
            cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.resize(frame, (400, 400))
        img = ImageTk.PhotoImage(Image.fromarray(frame))
        video_label.config(image=img)
        video_label.image = img
        root.update_idletasks()
        time.sleep(1 / 30)  # Mantém 30 FPS para animação fluida

# Iniciar o vídeo em um thread separado
video_thread = Thread(target=play_video, daemon=True)
video_thread.start()

def speak(text, speed=1.0):
    """Converte texto em fala usando gTTS e reproduz o áudio sem salvar o arquivo."""
    tts = gTTS(text=text, lang='pt', slow=(speed < 1.0))
    audio_fp = io.BytesIO()
    tts.write_to_fp(audio_fp)
    audio_fp.seek(0)
    
    pygame.mixer.init()
    pygame.mixer.music.load(audio_fp, 'mp3')
    pygame.mixer.music.play()
    while pygame.mixer.music.get_busy():
        root.update_idletasks()  # Mantém a interface responsiva

def ask_local_llm(question):
    """Consulta o servidor local LLM e retorna a resposta."""
    try:
        url = "http://localhost:1234/v1/chat/completions"
        payload = {
            "model": "hermes-3-llama-3.2-3b",
            "messages": [
                {"role": "system", "content": "Você é um assistente virtual. Sempre responda apenas em português do Brasil e limite sua resposta a 50 palavras. Seja engraçada"},
                {"role": "user", "content": question}
            ],
            "temperature": 0.7,
            "max_tokens": 50,
            "stream": False
        }
        headers = {"Content-Type": "application/json"}
        response = requests.post(url, json=payload, headers=headers)
        if response.status_code == 200:
            return response.json()["choices"][0]["message"]["content"].strip()
        else:
            return "Erro ao obter resposta do servidor local."
    except Exception as e:
        print("Erro ao se comunicar com o servidor local:", e)
        return "Desculpe, não consegui obter uma resposta no momento."

def evento_patrocinador():
    """Escolhe aleatoriamente um patrocinador para o evento."""
    patrocinadores = ["Este evento é patrocinado pela Loja A.",
                      "Este evento é patrocinado pela Loja B.",
                      "Este evento é patrocinado pela Loja C."]
    return np.random.choice(patrocinadores)

def iniciar_conversa():
    speak("Bem-vindo à SEMAD e à SE INFO", speed=1.0)
    patrocinio = evento_patrocinador()
    speak(patrocinio, speed=1.0)
    speak("Se precisar de ajuda, faça uma pergunta.", speed=1.0)
    
    comando = listen()
    if comando:
        resposta = ask_local_llm(comando)
        speak(resposta, speed=1.0)

def listen():
    """Captura o áudio do microfone e converte em texto."""
    r = sr.Recognizer()
    with sr.Microphone() as source:
        instrucao_label.config(text="Fale agora...")
        root.update()
        audio = r.listen(source)
    try:
        text = r.recognize_google(audio, language="pt-BR")
        instrucao_label.config(text="Você disse: " + text)
        root.update()
        return text
    except sr.UnknownValueError:
        instrucao_label.config(text="Não entendi o que foi dito.")
        return ""
    except sr.RequestError as e:
        instrucao_label.config(text="Erro na requisição do serviço.")
        return ""

# Criando rótulo para instruções
instrucao_label = tk.Label(root, text="Clique no botão para iniciar a conversa", font=("Arial", 12))
instrucao_label.pack()

# Criando botão para iniciar a conversa
botao_iniciar = tk.Button(root, text="Iniciar Conversa", font=("Arial", 14), command=iniciar_conversa)
botao_iniciar.pack(pady=20)

root.mainloop()
