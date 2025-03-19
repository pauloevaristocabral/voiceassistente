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
from threading import Thread, Event
from PIL import Image, ImageTk
import tempfile
import uuid

# === CONFIGURAÇÃO DA PORTA SERIAL ===
# Altere esta variável para definir qual porta COM usar
# Exemplo: "COM3", "COM4", etc.
# Deixe como None para detecção automática
PORTA_COM = "COM10"  # <-- ALTERE AQUI PARA SUA PORTA

# Sons de feedback - substitua por caminhos completos se necessário
LISTEN_CHIME_PATH = os.path.join(os.path.dirname(__file__), "listen_chime.mp3")
ERROR_SOUND_PATH = os.path.join(os.path.dirname(__file__), "error.mp3")

# Caminhos dos vídeos
WAITING_VIDEO_PATH = "wave.mp4"     # Vídeo reproduzido enquanto aguarda
SPEAKING_VIDEO_PATH = "wave1.mp4"   # Vídeo reproduzido durante a fala

# Pasta temporária para salvar arquivos de áudio
TEMP_DIR = tempfile.gettempdir()

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

# Inicializa o pygame para áudio
pygame.mixer.init()

# Rótulo para o vídeo
video_label = tk.Label(root)
video_label.pack()

# Variáveis globais
serial_port = None
current_video = WAITING_VIDEO_PATH
stop_video_thread = False
audio_finished = Event()
audio_finished.set()  # Inicialmente não está reproduzindo áudio
sensor_active = False  # Controla o estado de ativação do sensor

def change_video(video_path):
    """Altera o vídeo que está sendo reproduzido"""
    global current_video
    current_video = video_path
    print(f"Alterando para o vídeo: {video_path}")

def play_video():
    """Executa o vídeo de acordo com o estado atual."""
    global current_video, stop_video_thread
    
    waiting_cap = cv2.VideoCapture(WAITING_VIDEO_PATH)
    speaking_cap = cv2.VideoCapture(SPEAKING_VIDEO_PATH)
    
    if not waiting_cap.isOpened():
        print(f"Erro ao abrir o vídeo: {WAITING_VIDEO_PATH}")
    
    if not speaking_cap.isOpened():
        print(f"Erro ao abrir o vídeo: {SPEAKING_VIDEO_PATH}")
    
    while not stop_video_thread:
        # Escolhe qual vídeo reproduzir com base na variável global
        active_cap = speaking_cap if current_video == SPEAKING_VIDEO_PATH else waiting_cap
        
        # Lê um quadro do vídeo
        ret, frame = active_cap.read()
        
        # Se chegou ao fim do vídeo, volta para o início
        if not ret:
            active_cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            continue
            
        # Converte e redimensiona o quadro
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        frame = cv2.resize(frame, (400, 400))
        
        # Exibe o quadro no tkinter
        try:
            img = ImageTk.PhotoImage(Image.fromarray(frame))
            video_label.config(image=img)
            video_label.image = img
        except RuntimeError:
            # Captura erro se a janela tkinter for fechada durante a execução
            break
            
        # Mantém a taxa de quadros (30 FPS)
        time.sleep(1 / 30)
    
    # Libera os recursos de vídeo ao encerrar
    waiting_cap.release()
    speaking_cap.release()

# Iniciar o vídeo em um thread separado
video_thread = Thread(target=play_video, daemon=True)
video_thread.start()

def play_sound_nonblocking(sound_path):
    """Reproduz um som sem bloquear a thread principal"""
    try:
        if os.path.exists(sound_path):
            pygame.mixer.music.load(sound_path)
            pygame.mixer.music.play()
            # Não bloqueia, retorna imediatamente
        else:
            print(f"Arquivo de som não encontrado: {sound_path}")
    except Exception as e:
        print(f"Erro ao reproduzir som: {e}")

def audio_playback_thread(temp_file):
    """Thread separada para monitorar a reprodução do áudio"""
    global audio_finished
    
    try:
        # Carrega e reproduz o áudio
        pygame.mixer.music.load(temp_file)
        pygame.mixer.music.play()
        
        # Monitora até que a reprodução termine
        while pygame.mixer.music.get_busy():
            time.sleep(0.1)
            
        # Sinaliza que o áudio terminou
        audio_finished.set()
        
        # Remove o arquivo temporário
        try:
            os.remove(temp_file)
        except:
            pass  # Ignora erros ao remover o arquivo
            
    except Exception as e:
        print(f"Erro na reprodução de áudio: {e}")
        audio_finished.set()  # Garante que o evento seja definido mesmo em caso de erro

def speak(text, speed=1.0):
    """Converte texto em fala usando gTTS e reproduz o áudio."""
    global audio_finished
    
    try:
        # Muda para o vídeo de fala
        change_video(SPEAKING_VIDEO_PATH)
        
        # Reseta o evento (indica que o áudio está em reprodução)
        audio_finished.clear()
        
        # Cria um nome de arquivo único para evitar conflitos
        temp_file = os.path.join(TEMP_DIR, f"response_{uuid.uuid4().hex}.mp3")
        
        # Gera o arquivo de áudio
        tts = gTTS(text=text, lang='pt', slow=(speed < 1.0))
        tts.save(temp_file)
        
        # Inicia a reprodução de áudio em uma thread separada
        audio_thread = Thread(target=audio_playback_thread, args=(temp_file,), daemon=True)
        audio_thread.start()
        
        # Aguarda o término da reprodução sem bloquear a interface gráfica
        while not audio_finished.is_set():
            root.update()  # Mantém a interface responsiva
            time.sleep(0.1)
        
        # Volta para o vídeo de espera
        change_video(WAITING_VIDEO_PATH)
            
    except Exception as e:
        instrucao_label.config(text=f"Erro ao reproduzir áudio: {str(e)}")
        print(f"Erro de TTS: {e}")
        # Volta para o vídeo de espera em caso de erro
        change_video(WAITING_VIDEO_PATH)
        audio_finished.set()  # Garante que o evento seja definido mesmo em caso de erro

def ask_local_llm(question):
    """Consulta o servidor local LLM e retorna a resposta."""
    try:
        url = "http://localhost:1234/v1/chat/completions"
        payload = {
            "model": "hermes-3-llama-3.2-3b",
            "messages": [
                {"role": "system", "content": "Você é um assistente virtual. Sempre responda apenas em português do Brasil e limite sua resposta a 50 palavras. seja formal"},
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
    patrocinadores = ["Este evento é patrocinado pela conect tevê.",
                      "Este evento é patrocinado pelo Hospital dos Olhos.",
                      "Este evento é patrocinado pela Queiroz & Alves Corretora.",
                      "Este evento é patrocinado pelo Sistema Sofia.",
                      "Este evento é patrocinado pela Humanitas.",
                      "Este evento é patrocinado pelo Sistema Wamag.",
                      "Este evento é patrocinado pelo Sistema Crediamigo"]
    return np.random.choice(patrocinadores)

def iniciar_conversa():
    global sensor_active
    
    try:
        # Define o sensor como ativo durante a conversa
        sensor_active = True
        
        speak("Bem-vindo à SEMAD e à SE INFO", speed=1.0)
        patrocinio = evento_patrocinador()
        speak(patrocinio, speed=1.0)
        speak("Se precisar de ajuda, faça uma pergunta.", speed=1.0)
        
        # Toca som antes de começar a escutar
        if os.path.exists(LISTEN_CHIME_PATH):
            play_sound_nonblocking(LISTEN_CHIME_PATH)
        
        comando = listen()
        if comando:
            resposta = ask_local_llm(comando)
            speak(resposta, speed=1.0)
        
        # Após concluir a conversa, reseta o estado do sensor
        instrucao_label.config(text="Conversa concluída. Aguardando nova ativação do sensor...")
        sensor_active = False
        
    except Exception as e:
        instrucao_label.config(text=f"Erro na conversa: {str(e)}")
        print(f"Erro na conversa: {e}")
        sensor_active = False  # Garante que o sensor seja resetado mesmo em caso de erro

def listen():
    """Captura o áudio do microfone e converte em texto."""
    # Garante que está mostrando o vídeo de espera
    change_video(WAITING_VIDEO_PATH)
    
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
        # Toca som de erro quando não entende
        if os.path.exists(ERROR_SOUND_PATH):
            play_sound_nonblocking(ERROR_SOUND_PATH)
        return ""
    except sr.RequestError as e:
        instrucao_label.config(text="Erro na requisição do serviço.")
        # Toca som de erro quando há falha na requisição
        if os.path.exists(ERROR_SOUND_PATH):
            play_sound_nonblocking(ERROR_SOUND_PATH)
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
    """Tenta conectar à porta serial especificada ou à primeira disponível"""
    global serial_port
    
    if not serial:
        instrucao_label.config(text="Módulo serial não disponível. Instale com 'pip install pyserial'")
        # Toca som de erro quando o módulo não está disponível
        if os.path.exists(ERROR_SOUND_PATH):
            play_sound_nonblocking(ERROR_SOUND_PATH)
        return False
    
    # Se a porta COM foi especificada no início do código
    if PORTA_COM:
        try:
            serial_port = serial.Serial(PORTA_COM, 9600, timeout=1)
            instrucao_label.config(text=f"Conectado à porta {PORTA_COM} com sucesso!\nMonitorando sinais do Arduino...")
            return True
        except Exception as e:
            instrucao_label.config(text=f"Erro ao conectar à porta {PORTA_COM}: {str(e)}\nTentando outras portas...")
            # Toca som de erro quando falha a conexão
            if os.path.exists(ERROR_SOUND_PATH):
                play_sound_nonblocking(ERROR_SOUND_PATH)
            # Se falhar, continua com a detecção automática
    
    # Detecção automática de portas
    available_ports = list_available_ports()
    if not available_ports:
        instrucao_label.config(text="Nenhuma porta serial disponível. Verifique se o Arduino está conectado.")
        # Toca som de erro quando não há portas disponíveis
        if os.path.exists(ERROR_SOUND_PATH):
            play_sound_nonblocking(ERROR_SOUND_PATH)
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
    # Toca som de erro quando não consegue conectar a nenhuma porta
    if os.path.exists(ERROR_SOUND_PATH):
        play_sound_nonblocking(ERROR_SOUND_PATH)
    return False

def monitor_serial():
    """Monitora a porta serial em busca do sinal LED_ON"""
    global serial_port, sensor_active
    
    if not serial:
        instrucao_label.config(text="Módulo serial não disponível. Instale com 'pip install pyserial'")
        # Toca som de erro
        if os.path.exists(ERROR_SOUND_PATH):
            play_sound_nonblocking(ERROR_SOUND_PATH)
        return
    
    if not connect_to_serial():
        return
    
    try:
        instrucao_label.config(text=f"Monitorando porta {serial_port.port} por sinais do sensor...")
        while True:
            if serial_port and serial_port.is_open and serial_port.in_waiting > 0:
                line = serial_port.readline().decode('utf-8', errors='replace').strip()
                instrucao_label.config(text=f"Recebido: {line}")
                
                # Apenas inicia a conversa se o sensor não estiver ativo e receber LED_ON
                if "LED_ON" in line and not sensor_active:
                    instrucao_label.config(text="Sensor ativado! Iniciando conversa...")
                    root.update()
                    # Toca som de notificação quando o sensor é ativado
                    if os.path.exists(LISTEN_CHIME_PATH):
                        play_sound_nonblocking(LISTEN_CHIME_PATH)
                    # Inicia a conversa em uma thread separada para não bloquear o monitoramento
                    Thread(target=iniciar_conversa, daemon=True).start()
            
            time.sleep(0.1)  # Pequeno delay
            root.update()  # Mantém a interface responsiva
            
    except Exception as e:
        instrucao_label.config(text=f"Erro no monitoramento: {str(e)}")
        # Toca som de erro quando há falha no monitoramento
        if os.path.exists(ERROR_SOUND_PATH):
            play_sound_nonblocking(ERROR_SOUND_PATH)
    finally:
        if serial_port and serial_port.is_open:
            serial_port.close()

# Criando rótulo para instruções
instrucao_label = tk.Label(root, wraplength=500, text="Iniciando aplicação...", font=("Arial", 12))
instrucao_label.pack(pady=20)

# Status da porta configurada
if PORTA_COM:
    porta_configurada_label = tk.Label(root, text=f"Porta configurada: {PORTA_COM}", font=("Arial", 10))
    porta_configurada_label.pack(pady=5)

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
    
    # Botão para conversa manual
    botao_manual = tk.Button(root, text="Iniciar Conversa Manualmente", font=("Arial", 14), command=iniciar_conversa)
    botao_manual.pack(pady=10)
else:
    # Se não tiver o módulo serial, mostra mensagem e botão manual
    instrucao_label.config(text="Módulo Serial não instalado.\nPor favor, instale com 'pip install pyserial'.\nUsando modo manual.")
    botao_iniciar = tk.Button(root, text="Iniciar Conversa Manualmente", font=("Arial", 14), command=iniciar_conversa)
    botao_iniciar.pack(pady=20)

# Verifica se os arquivos existem
if not os.path.exists(WAITING_VIDEO_PATH):
    instrucao_label.config(text=f"Arquivo de vídeo não encontrado: {WAITING_VIDEO_PATH}")
if not os.path.exists(SPEAKING_VIDEO_PATH):
    instrucao_label.config(text=f"Arquivo de vídeo não encontrado: {SPEAKING_VIDEO_PATH}")
if not os.path.exists(LISTEN_CHIME_PATH):
    instrucao_label.config(text=f"Arquivo de som não encontrado: {LISTEN_CHIME_PATH}")
if not os.path.exists(ERROR_SOUND_PATH):
    instrucao_label.config(text=f"Arquivo de som não encontrado: {ERROR_SOUND_PATH}")

# Função para limpar recursos ao encerrar
def on_closing():
    global stop_video_thread
    stop_video_thread = True
    
    # Fechando a porta serial
    if serial_port and serial_port.is_open:
        serial_port.close()
    
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_closing)
root.mainloop()