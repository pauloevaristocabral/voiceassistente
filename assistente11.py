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

# Tentativa de importar serial - tratando possíveis erros
try:
    import serial
    try:
        import serial.tools.list_ports
        SERIAL_TOOLS_AVAILABLE = True
    except ImportError:
        SERIAL_TOOLS_AVAILABLE = False
        print("Módulo serial.tools não encontrado. Usando método alternativo.")
except ImportError:
    serial = None
    SERIAL_TOOLS_AVAILABLE = False
    print("Módulo serial não encontrado. Por favor, instale com 'pip install pyserial'")

# Criando a interface gráfica
root = tk.Tk()
root.title("Assistente Virtual")
root.geometry("600x600")

# Carregar vídeo
video_path = "wave.mp4"
cap = cv2.VideoCapture(video_path)
video_label = tk.Label(root)
video_label.pack()

# Variável global para a porta serial
serial_port = None

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

def list_available_ports():
    """Lista todas as portas seriais disponíveis no sistema"""
    if not serial:
        return []
        
    available_ports = []
    port_info = "Portas disponíveis:\n"
    
    if SERIAL_TOOLS_AVAILABLE:
        # Método usando serial.tools.list_ports
        ports = serial.tools.list_ports.comports()
        if not ports:
            port_info += "  Nenhuma porta serial detectada"
        else:
            for port in ports:
                port_info += f"  {port.device} - {port.description}\n"
                available_ports.append(port.device)
    else:
        # Método alternativo para Windows
        # Tenta as portas COM mais comuns
        for i in range(1, 20):
            port = f"COM{i}"
            try:
                s = serial.Serial(port)
                s.close()
                port_info += f"  {port}\n"
                available_ports.append(port)
            except:
                pass
                
        if not available_ports:
            port_info += "  Nenhuma porta serial detectada"
    
    instrucao_label.config(text=port_info)
    root.update()
    return available_ports

def connect_to_serial():
    """Tenta conectar à primeira porta serial disponível"""
    global serial_port
    
    if not serial:
        instrucao_label.config(text="Módulo serial não disponível. Instale com 'pip install pyserial'")
        return False
    
    available_ports = list_available_ports()
    if not available_ports:
        instrucao_label.config(text="Nenhuma porta serial disponível. Verifique se o Arduino está conectado.")
        return False
    
    # Tenta conectar em cada porta disponível
    for port in available_ports:
        try:
            serial_port = serial.Serial(port, 9600, timeout=1)
            instrucao_label.config(text=f"Conectado à porta {port} com sucesso!\nMonitorando sinais do Arduino...")
            return True
        except Exception as e:
            continue
    
    instrucao_label.config(text="Não foi possível conectar a nenhuma porta serial. Verifique as permissões.")
    return False

def monitor_serial():
    """Monitora a porta serial em busca do sinal LED_ON"""
    global serial_port
    
    if not serial:
        instrucao_label.config(text="Módulo serial não disponível. Instale com 'pip install pyserial'")
        return
    
    if not connect_to_serial():
        return
    
    try:
        while True:
            if serial_port and serial_port.is_open and serial_port.in_waiting > 0:
                line = serial_port.readline().decode('utf-8', errors='replace').strip()
                instrucao_label.config(text=f"Recebido: {line}")
                
                if "LED_ON" in line:
                    instrucao_label.config(text="Sensor ativado! Iniciando conversa...")
                    root.update()
                    iniciar_conversa()
            
            time.sleep(0.1)  # Pequeno delay
            root.update()  # Mantém a interface responsiva
            
    except Exception as e:
        instrucao_label.config(text=f"Erro: {str(e)}")
    finally:
        if serial_port and serial_port.is_open:
            serial_port.close()

# Criando rótulo para instruções
instrucao_label = tk.Label(root, wraplength=500, text="Iniciando aplicação...", font=("Arial", 12))
instrucao_label.pack(pady=20)

# Botões
if serial:
    # Se tiver o módulo serial, inicia monitoramento
    instrucao_label.config(text="Iniciando monitoramento da porta serial...")
    serial_thread = Thread(target=monitor_serial, daemon=True)
    serial_thread.start()
    
    # Botão para reconectar
    botao_reconectar = tk.Button(root, text="Reconectar Serial", font=("Arial", 14), 
                               command=lambda: Thread(target=monitor_serial, daemon=True).start())
    botao_reconectar.pack(pady=10)
else:
    # Se não tiver o módulo serial, mostra mensagem e botão manual
    instrucao_label.config(text="Módulo Serial não instalado.\nPor favor, instale com 'pip install pyserial'.\nUsando modo manual.")
    botao_iniciar = tk.Button(root, text="Iniciar Conversa Manualmente", font=("Arial", 14), command=iniciar_conversa)
    botao_iniciar.pack(pady=20)

root.mainloop()

# Garantir que a porta serial seja fechada ao sair
if serial_port and serial_port.is_open:
    serial_port.close()