-- Database Initialization for Transmision Tornado

CREATE DATABASE IF NOT EXISTS transmisionesfast_tornado;
USE transmisionesfast_tornado;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255) UNIQUE,
    phone VARCHAR(50),
    role ENUM('superadmin', 'admin', 'moderator', 'speaker', 'viewer') DEFAULT 'viewer',
    password VARCHAR(255) DEFAULT 'produccionesfast2050',
    chat_blocked TINYINT(1) DEFAULT 0,
    qa_blocked TINYINT(1) DEFAULT 0,
    banned TINYINT(1) DEFAULT 0,
    event_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Events table
CREATE TABLE IF NOT EXISTS events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    slug VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    stream_url VARCHAR(255),
    title VARCHAR(255),
    logo_url VARCHAR(255),
    video_url VARCHAR(255),
    theme_color VARCHAR(50),
    header_bg_color VARCHAR(50),
    header_text_color VARCHAR(50),
    body_bg_color VARCHAR(50),
    body_text_color VARCHAR(50),
    is_active TINYINT(1) DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    timezone VARCHAR(50) DEFAULT 'America/Mexico_City'
);

-- Event Staff table
CREATE TABLE IF NOT EXISTS event_staff (
    user_id INT NOT NULL,
    event_id INT NOT NULL,
    role ENUM('admin', 'moderator', 'speaker') NOT NULL,
    PRIMARY KEY (user_id, event_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
    FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
);

-- Questions table
CREATE TABLE IF NOT EXISTS questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    manual_user_name VARCHAR(255),
    question_text TEXT NOT NULL,
    status ENUM('pending', 'approved', 'rejected', 'read') NOT NULL DEFAULT 'pending',
    event_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Chat messages table
CREATE TABLE IF NOT EXISTS chat_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    message TEXT NOT NULL,
    event_id INT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Session analytics table
CREATE TABLE IF NOT EXISTS session_analytics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    event_id INT,
    start_time TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_ping TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    total_minutes INT DEFAULT 0,
    UNIQUE KEY (user_id, event_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Optional settings table (exists in current production DB; not required by app code today)
CREATE TABLE IF NOT EXISTS settings (
    setting_key VARCHAR(255) PRIMARY KEY,
    setting_value TEXT
);

-- Seed an example event
INSERT IGNORE INTO events (id, name, slug, description, stream_url, is_active) 
VALUES (1, 'Evento Demo Fast', 'demo-fast', 'Transmisión de prueba', 'https://www.youtube.com/embed/live_stream?channel=UCXXXXXXXX', 1);

-- Seed an example user (Admin)
INSERT IGNORE INTO users (id, name, email, role, event_id, created_at) 
VALUES (1, 'Diego Bravo', 'diego@produccionesfast.com', 'superadmin', NULL, NOW());

-- Assign user as Admin/Speaker for the demo event
INSERT IGNORE INTO event_staff (user_id, event_id, role) 
VALUES (1, 1, 'admin');
