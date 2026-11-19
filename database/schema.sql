
CREATE DATABASE IF NOT EXISTS college_events
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE college_events;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(100) NOT NULL,
  email VARCHAR(190) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('student','organizer','admin') NOT NULL DEFAULT 'student',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS clubs (
  id INT AUTO_INCREMENT PRIMARY KEY,
  name VARCHAR(120) NOT NULL UNIQUE,
  description TEXT,
  organizer_id INT NOT NULL,
  approved TINYINT(1) NOT NULL DEFAULT 1,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (organizer_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS events (
  id INT AUTO_INCREMENT PRIMARY KEY,
  club_id INT NOT NULL,
  organizer_id INT NOT NULL,
  title VARCHAR(180) NOT NULL,
  category VARCHAR(80) NOT NULL,
  description TEXT NOT NULL,
  event_date DATETIME NOT NULL,
  venue VARCHAR(180) NOT NULL,
  registration_url VARCHAR(500),
  poster_filename VARCHAR(255),
  status ENUM('upcoming','completed','cancelled') NOT NULL DEFAULT 'upcoming',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (club_id) REFERENCES clubs(id) ON DELETE CASCADE,
  FOREIGN KEY (organizer_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_event_date (event_date),
  INDEX idx_event_category (category)
);

CREATE TABLE IF NOT EXISTS registrations (
  id INT AUTO_INCREMENT PRIMARY KEY,
  event_id INT NOT NULL,
  student_id INT NOT NULL,
  registered_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  UNIQUE KEY unique_registration (event_id, student_id),
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
  FOREIGN KEY (student_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS comments (
  id INT AUTO_INCREMENT PRIMARY KEY,
  event_id INT NOT NULL,
  user_id INT NOT NULL,
  parent_id INT NULL,
  body TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  FOREIGN KEY (parent_id) REFERENCES comments(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS likes (
  id INT AUTO_INCREMENT PRIMARY KEY,
  event_id INT NOT NULL,
  user_id INT NOT NULL,
  UNIQUE KEY unique_like (event_id, user_id),
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS ratings (
  id INT AUTO_INCREMENT PRIMARY KEY,
  event_id INT NOT NULL,
  user_id INT NOT NULL,
  rating TINYINT NOT NULL CHECK (rating BETWEEN 1 AND 5),
  review VARCHAR(1000),
  UNIQUE KEY unique_rating (event_id, user_id),
  FOREIGN KEY (event_id) REFERENCES events(id) ON DELETE CASCADE,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
  id INT AUTO_INCREMENT PRIMARY KEY,
  user_id INT NOT NULL,
  message VARCHAR(500) NOT NULL,
  link VARCHAR(255),
  is_read TINYINT(1) NOT NULL DEFAULT 0,
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
);
