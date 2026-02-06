-- Database Initialization for Transmision Tornado

CREATE DATABASE IF NOT EXISTS transmision_tornado;
USE transmision_tornado;

-- Users table
CREATE TABLE IF NOT EXISTS users (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    email VARCHAR(255),
    phone VARCHAR(50),
    password VARCHAR(255) DEFAULT 'produccionesfast2050',
    role ENUM('visor', 'moderador', 'speaker', 'administrador') DEFAULT 'visor',
    event_id INT,
    chat_blocked TINYINT(1) DEFAULT 0,
    qa_blocked TINYINT(1) DEFAULT 0,
    banned TINYINT(1) DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    INDEX idx_email_event (email, event_id)
);

-- Events table
CREATE TABLE IF NOT EXISTS events (
    id INT AUTO_INCREMENT PRIMARY KEY,
    slug VARCHAR(100) NOT NULL UNIQUE,
    title VARCHAR(255) NOT NULL,
    logo_url VARCHAR(500),
    video_url VARCHAR(500),
    is_active TINYINT(1) DEFAULT 1,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Event Staff table (kept for potential future use, but current code uses users.role directly)
-- CREATE TABLE IF NOT EXISTS event_staff (
--     user_id INT NOT NULL,
--     event_id INT NOT NULL,
--     role ENUM('admin', 'moderator', 'speaker') NOT NULL,
--     PRIMARY KEY (user_id, event_id),
--     FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
--     FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE
-- );

-- Questions table
CREATE TABLE IF NOT EXISTS questions (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    user_name VARCHAR(255),
    question_text TEXT NOT NULL,
    status ENUM('pending', 'approved', 'rejected', 'read') NOT NULL DEFAULT 'pending',
    event_id INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Chat messages table
CREATE TABLE IF NOT EXISTS chat_messages (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    user_name VARCHAR(255),
    message TEXT NOT NULL,
    event_id INT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Session analytics table
CREATE TABLE IF NOT EXISTS session_analytics (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    event_id INT,
    start_time DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_ping DATETIME DEFAULT CURRENT_TIMESTAMP,
    total_minutes INT DEFAULT 0,
    UNIQUE KEY (user_id, event_id),
    FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

-- Seed an example event
INSERT IGNORE INTO events (id, slug, title, logo_url, video_url, is_active) 
VALUES (1, 'demo-fast', 'Evento Demo Fast', 'https://produccionesfast.com/logo.png', 'https://www.youtube.com/embed/live_stream?channel=UCXXXXXXXX', 1);

-- Seed an example admin user (can access all events with event_id = NULL)
INSERT IGNORE INTO users (id, name, email, password, role, event_id, created_at) 
VALUES (1, 'Diego Bravo', 'diego@produccionesfast.com', 'produccionesfast2050', 'administrador', NULL, NOW());
