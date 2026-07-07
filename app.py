import streamlit as st
import pandas as pd
import sqlite3
from datetime import datetime
from google import genai
from google.genai import types
import plotly.express as px


# 1. KONFIGURASI AI
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]
genai.configure(api_key=GEMINI_API_KEY)
client = genai.Client(api_key=GEMINI_API_KEY, http_options={'headers': {'Authorization': f'Bearer {GEMINI_API_KEY}'}})
model = genai.GenerativeModel("gemini-1.5-flash")


# 2. KONEKSI DATABASE & PEMBUATAN TABEL
conn = sqlite3.connect('life_os.db', check_same_thread=False)
c = conn.cursor()

c.execute('''CREATE TABLE IF NOT EXISTS inbox (id INTEGER PRIMARY KEY, isi TEXT, tanggal TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS proyek (id INTEGER PRIMARY KEY, nama TEXT, tenggat TEXT, status TEXT)''')
c.execute('''CREATE TABLE IF NOT EXISTS kebiasaan (id INTEGER PRIMARY KEY, nama TEXT, tanggal TEXT, status INTEGER)''')
c.execute('''CREATE TABLE IF NOT EXISTS keuangan 
             (id INTEGER PRIMARY KEY, tipe TEXT, kategori TEXT, jumlah INTEGER, tanggal TEXT, keterangan TEXT)''')
conn.commit()
import re
from youtube_transcript_api import YouTubeTranscriptApi

def rangkum_video_youtube(url_video: str) -> str:
    """
    Mengambil transkrip dari video YouTube secara otomatis dan membersihkan ID video dari parameter pengotor.
    """
    try:
        # 1. Bersihkan spasi di awal/akhir input
        url_video = url_video.strip()
        
        # 2. Regex super kuat untuk mengekstrak tepat 11 karakter ID video YouTube
        pola = r'(?:v=|\/shorts\/|youtu\.be\/|\/embed\/)([a-zA-Z0-9_-]{11})'
        pencocokan = re.search(pola, url_video)
        video_id = pencocokan.group(1) if pencocokan else None
        
        if not video_id:
            return "Gagal merangkum: Format URL YouTube tidak valid atau ID video tidak ditemukan."
        
        # 3. Ambil Transkrip Video (Mencoba Bahasa Indonesia 'id', lalu Inggris 'en')
        try:
            transkrip_data = YouTubeTranscriptApi.get_transcript(video_id, languages=['id', 'en'])
        except Exception:
            # Jika gagal (tidak ada subtitle manual), ambil daftar transkrip otomatis yang tersedia
            daftar_transkrip = YouTubeTranscriptApi.list_transcripts(video_id)
            # Ambil bahasa Indonesia atau Inggris dari transkrip otomatis/manual yang ada
            transkrip_data = daftar_transkrip.find_transcript(['id', 'en']).fetch()

        # Gabungkan seluruh teks menjadi satu kesatuan cerita materi
        teks_video = " ".join([item['text'] for item in transkrip_data])
        
        # Batasi panjang karakter teks agar aman dari limit token AI
        if len(teks_video) > 35000:
            teks_video = teks_video[:35000] + "... (teks dipotong karena terlalu panjang)"

        # Kembalikan teks mentah agar diproses oleh sistem chat Gemini Anda
        return (
            f"Berikut adalah materi transkrip lengkap dari video YouTube tersebut. "
            f"Tolong rangkum pelajaran ini menjadi poin-poin penting, jelaskan istilah "
            f"rumit yang muncul, dan buat ringkasannya dalam Bahasa Indonesia yang santun:\n\n{teks_video}"
        )
        
    except Exception as e:
        # Pesan ramah jika video benar-benar tidak memiliki subtitle/transkrip sama sekali (misal video musik atau tanpa suara)
        return (
            f"Gagal mengambil materi video (ID: {video_id}). Video ini kemungkinan besar "
            f"tidak memiliki transkrip atau teks teks otomatis yang diaktifkan oleh pemiliknya. "
            f"Detail kendala: {str(e)}"
        )


# =====================================================================
# 🛠️ ALAT (TOOLS) UNTUK OTOMATISASI DATABASE OLEH AI
# =====================================================================

def tambah_proyek_otomatis(nama_proyek: str, tenggat_waktu: str) -> str:
    """Menambahkan proyek baru ke dalam database. Format tenggat_waktu: YYYY-MM-DD."""
    try:
        c.execute("INSERT INTO proyek (nama, tenggat, status) VALUES (?, ?, ?)", (nama_proyek, tenggat_waktu, "Aktif"))
        conn.commit()
        return f"SUKSES: Proyek '{nama_proyek}' tenggat {tenggat_waktu} tersimpan."
    except Exception as e: return f"GAGAL: {str(e)}"

def tambah_inbox_otomatis(isi_catatan: str) -> str:
    """Memasukkan catatan cepat atau tugas mendadak ke dalam tabel inbox."""
    try:
        waktu_sekarang = datetime.now().strftime('%Y-%m-%d %H:%M')
        c.execute("INSERT INTO inbox (isi, tanggal) VALUES (?, ?)", (isi_catatan, waktu_sekarang))
        conn.commit()
        return f"SUKSES: Catatan berhasil disimpan ke dalam Inbox."
    except Exception as e: return f"GAGAL: {str(e)}"

def catat_keuangan_otomatis(tipe: str, kategori: str, jumlah: int, keterangan: str) -> str:
    """Mencatat transaksi keuangan otomatis. tipe: 'Pemasukan' atau 'Pengeluaran'."""
    try:
        tipe_clean = tipe.capitalize()
        if tipe_clean not in ['Pemasukan', 'Pengeluaran']:
            return "GAGAL: Tipe harus berupa 'Pemasukan' atau 'Pengeluaran'"
        
        hari_ini = datetime.today().strftime('%Y-%m-%d')
        c.execute("INSERT INTO keuangan (tipe, kategori, jumlah, tanggal, keterangan) VALUES (?, ?, ?, ?, ?)",
                  (tipe_clean, kategori.upper(), jumlah, hari_ini, keterangan))
        conn.commit()
        return f"SUKSES: Mencatat {tipe_clean} {kategori.upper()} Rp {jumlah:,} untuk '{keterangan}'."
    except Exception as e: return f"GAGAL: {str(e)}"


# =====================================================================
# 🤖 ENGINE INTERAKSI AI GEMINI
# =====================================================================

def jalankan_ai_asisten(konteks_user, pertanyaan_user):
    if GEMINI_API_KEY == "ISI_API_KEY_GEMINI_ANDA_DI_SINI":
        return "⚠️ Mohon masukkan Gemini API Key Anda terlebih dahulu di dalam kode!"
    
    try:
        from google.genai import errors

        prompt_sistem = (
            "Anda adalah BERCOM, Manajer Eksekutif AI dan Asisten Pribadi cerdas untuk Life OS pengguna.\n"
            "Anda memiliki akses otonom untuk menggunakan fungsi keuangan, proyek, dan inbox.\n"
            "Jika pengguna menyebutkan nominal transaksi, langsung panggil fungsi 'catat_keuangan_otomatis'.\n"
            "Gunakan bahasa Indonesia yang santai, ringkas, panggil pengguna Anda dengan sebutan 'Bos' atau 'Master', "
            "dan selalu konfirmasikan angka dengan format Rp."
        )

        input_lengkap = f"{prompt_sistem}\n\n[DATA LIFE OS PENGGUNA SAAT INI]:\n{konteks_user}\n\n[PERINTAH]:\n{pertanyaan_user}"
        daftar_tools = [tambah_proyek_otomatis, tambah_inbox_otomatis, catat_keuangan_otomatis, rangkum_video_youtube]
        config = types.GenerateContentConfig(tools=daftar_tools, temperature=0.4)
        response = client.models.generate_content(model='gemini-2.5-flash', contents=input_lengkap, config=config)
        
        if response.function_calls:
            for call in response.function_calls:
                nama_fungsi = call.name
                argumen = call.args
                if nama_fungsi == "catat_keuangan_otomatis":
                    hasil_aksi = catat_keuangan_otomatis(argumen['tipe'], argumen['kategori'], int(argumen['jumlah']), argumen['keterangan'])
                elif nama_fungsi == "tambah_proyek_otomatis":
                    hasil_aksi = tambah_proyek_otomatis(argumen['nama_proyek'], argumen['tenggat_waktu'])
                elif nama_fungsi == "tambah_inbox_otomatis":
                    hasil_aksi = tambah_inbox_otomatis(argumen['isi_catatan'])
                elif nama_fungsi == "rangkum_video_youtube":
                    hasil_aksi = rangkum_video_youtube(argumen['url_video'])
                else:
                    hasil_aksi = "Fungsi tidak dikenali."

                respons_final = client.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[
                        types.Content(role="user", parts=[types.Part.from_text(text=input_lengkap)]),
                        response.candidates.content,
                        types.Content(role="user", parts=[types.Part.from_text(text=f"[HASIL SISTEM]: {hasil_aksi}")])
                    ], config=config
                )
                return respons_final.text
   except Exception as e: return f"Terjadi kesalahan pada sistem AI: {str(e)}"

# =====================================================================
# 🖥️ ANTARMUKA WEB STREAMLIT (DASBOR INTERAKTIF)
# =====================================================================

st.set_page_config(page_title="Life OS v5.0", page_icon="🏛️", layout="wide")
st.title("🏛️ Ultimate Life OS — AI Executive Suite")

menu = ["Dasbor Utama", "💬 Obrolan AI Asisten", "💰 Jurnal Keuangan", "🗂️ PARA: Proyek"]
pilihan = st.sidebar.selectbox("Navigasi", menu)

# Mengambil data terkini dari Database
df_proyek = pd.read_sql_query("SELECT nama, tenggat, status FROM proyek", conn)
df_inbox = pd.read_sql_query("SELECT isi, tanggal FROM inbox", conn)
df_keuangan = pd.read_sql_query("SELECT * FROM keuangan", conn)

# Perhitungan Nilai Finansial
pemasukan = df_keuangan[df_keuangan['tipe'] == 'Pemasukan']['jumlah'].sum()
pengeluaran = df_keuangan[df_keuangan['tipe'] == 'Pengeluaran']['jumlah'].sum()
saldo_total = pemasukan - pengeluaran

konteks_life_os = (
    f"Hari ini tanggal: {datetime.today().strftime('%Y-%m-%d')}\n"
    f"Total Saldo Pengguna saat ini: Rp {saldo_total:,}\n"
    f"Riwayat Keuangan Terakhir: {df_keuangan.tail(5).to_dict(orient='records')}\n"
    f"Proyek saat ini: {df_proyek.to_dict(orient='records')}"
)

# --- FITUR 1: DASBOR UTAMA ---
if pilihan == "Dasbor Utama":
    st.subheader("🗓️ Ikhtisar Pusat Kendali — " + datetime.today().strftime('%A, %d %B %Y'))
    
    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Total Income", f"Rp {pemasukan:,}")
    col_b.metric("Total Expenses", f"Rp {pengeluaran:,}", delta=f"-Rp {pengeluaran:,}", delta_color="inverse")
    col_c.metric("Net Worth (Saldo Bersih)", f"Rp {saldo_total:,}")
    st.markdown("---")
    
    st.markdown("### 📊 Analisis Inteligensi Finansial")
    if not df_keuangan.empty:
        col_g1, col_g2 = st.columns(2)
        with col_g1:
            df_summary = df_keuangan.groupby('tipe')['jumlah'].sum().reset_index()
            fig_bar = px.bar(df_summary, x='tipe', y='jumlah', color='tipe',
                             title="Perbandingan Kas Masuk vs Kas Keluar",
                             labels={'jumlah': 'Total Nilai (Rp)', 'tipe': 'Jenis Aliran Dana'},
                             color_discrete_map={'Pemasukan': '#2ecc71', 'Pengeluaran': '#e74c3c'})
            st.plotly_chart(fig_bar, use_container_width=True)
            
        with col_g2:
            df_expense = df_keuangan[df_keuangan['tipe'] == 'Pengeluaran']
            if not df_expense.empty:
                df_pie = df_expense.groupby('kategori')['jumlah'].sum().reset_index()
                fig_pie = px.pie(df_pie, values='jumlah', names='kategori', 
                                 title="Alokasi Distribusi Pengeluaran",
                                 hole=0.4, color_discrete_sequence=px.colors.sequential.RdBu)
                st.plotly_chart(fig_pie, use_container_width=True)
            else: st.info("Belum ada data pengeluaran untuk dianalisis di grafik.")
    else: st.info("💡 Belum ada riwayat keuangan terdeteksi. Silakan isi lewat AI.")

    st.markdown("---")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 🎯 Fokus Proyek Saat Ini")
        st.dataframe(df_proyek, use_container_width=True)
    with col2:
        st.markdown("### 📥 Isi Otak Digital (Inbox)")
        st.dataframe(df_inbox, use_container_width=True)

# --- FITUR 2: CHAT DENGAN AI + INPUT SUARA ---
elif pilihan == "💬 Obrolan AI Asisten":
    # Import pustaka perekam suara lokal di dalam menu chat
    from streamlit_mic_recorder import mic_recorder
    
    st.subheader("💬 Hub Asisten Pribadi Otonom")
    st.caption("Gunakan kolom teks di bawah atau tekan tombol mikrofon untuk memberikan perintah suara langsung.")
    
    # Inisialisasi riwayat obrolan jika belum ada
    if "messages" not in st.session_state: 
        st.session_state.messages = []
        
    # Variabel penampung teks perintah suara
    perintah_suara_teks = None

    # 🎙️ KOMPONEN PEREKAM SUARA
    st.write("🎙️ **Perintah Suara:** Klik untuk mulai bicara, klik lagi jika sudah selesai.")
    audio_rekaman = mic_recorder(
        start_prompt="🔴 Mulai Rekam Suara",
        stop_prompt="⏹️ Selesai & Kirim",
        key='perekam_life_os'
    )

    # Jika user selesai merekam suara
    if audio_rekaman:
        bytes_audio = audio_rekaman['bytes']
        
        with st.spinner("🤖 Mengonversi suara Anda menjadi teks..."):
            try:
                # Memanggil klien Google GenAI SDK
                client_ai = genai.Client(api_key=GEMINI_API_KEY)
                
                # Mengirimkan file audio mentah langsung ke Gemini 2.5 Flash untuk ditranskripsi
                respons_transkripsi = client_ai.models.generate_content(
                    model='gemini-2.5-flash',
                    contents=[
                        types.Part.from_bytes(
                            data=bytes_audio,
                            mime_type="audio/wav"
                        ),
                        "Dengarkan rekaman audio ini dengan sangat teliti dan tuliskan kembali seluruh isi perkataannya dalam bahasa Indonesia tanpa tambahan komentar apapun."
                    ]
                )
                perintah_suara_teks = respons_transkripsi.text.strip()
                st.info(f"🗣️ **Hasil Deteksi Suara Anda:** \"{perintah_suara_teks}\"")
            except Exception as error_audio:
                st.error(f"Gagal memproses suara: {str(error_audio)}")

    # Tampilkan seluruh riwayat percakapan chat di layar
    for message in st.session_state.messages:
        with st.chat_message(message["role"]): 
            st.markdown(message["content"])

    # ⚡ PROSES INPUT (Menerima dari Teks Manual ATAU Transkripsi Suara)
    prompt_input = st.chat_input("Atau ketik perintah manual di sini...")
    
    # Tentukan input mana yang aktif
    prompt_aktif = None
    if perintah_suara_teks:
        prompt_aktif = perintah_suara_teks
    elif prompt_input:
        prompt_aktif = prompt_input

    # Eksekusi perintah jika ada input masuk
    if prompt_aktif:
        # 1. Tampilkan pesan pengguna di layar
        with st.chat_message("user"): 
            st.markdown(prompt_aktif)
        st.session_state.messages.append({"role": "user", "content": prompt_aktif})

        # 2. Minta AI mengeksekusi fungsi otonom berdasarkan teks tersebut
        with st.chat_message("assistant"):
            with st.spinner("Menjalankan tugas otonom..."):
                jawaban = jalankan_ai_asisten(konteks_life_os, prompt_aktif)
                st.markdown(jawaban)
        st.session_state.messages.append({"role": "assistant", "content": jawaban})
        
        # Bersihkan state dan segarkan halaman agar tampilan sinkron
        st.rerun()


# --- FITUR 3: JURNAL KEUANGAN MANUAL ---
elif pilihan == "💰 Jurnal Keuangan":
    st.subheader("📊 Pembukuan Kas Digital Lokal")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        st.markdown("### Input Manual")
        with st.form("Form Manual Keuangan", clear_on_submit=True):
            t_tipe = st.selectbox("Jenis", ["Pengeluaran", "Pemasukan"])
            t_kat = st.text_input("Kategori (Contoh: Makanan, Belanja)")
            t_jum = st.number_input("Jumlah Tunai (Rp)", min_value=0, step=5000)
            t_ket = st.text_input("Detail Deskripsi")
            if st.form_submit_button("Suntik Data"):
                catat_keuangan_otomatis(t_tipe, t_kat, t_jum, t_ket)
                st.success("Transaksi masuk!")
                st.rerun()
    with col_f2:
        st.markdown("### Histori Lengkap Buku Besar")
        st.dataframe(df_keuangan.sort_values(by="id", ascending=False), use_container_width=True)

# --- FITUR 4: DATABASE PROYEK ---
elif pilihan == "🗂️ PARA: Proyek":
    st.subheader("📁 Modul PARA: Manajemen Proyek")
    st.dataframe(df_proyek, use_container_width=True)

    # =====================================================================
# 🚨 TOMBOL RAHASIA RESET DATA (TAMBAHKAN DI PALING BAWAH FILE)
# =====================================================================
st.sidebar.markdown("---")
if st.sidebar.button("🚨 Reset Semua Data", help="Klik untuk mengosongkan seluruh database"):
    c.execute("DELETE FROM keuangan")
    c.execute("DELETE FROM proyek")
    c.execute("DELETE FROM inbox")
    conn.commit()
    st.sidebar.success("Database berhasil dikosongkan!")
    st.rerun()
