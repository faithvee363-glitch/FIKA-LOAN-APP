-- FIKA Loan App – MySQL / MariaDB schema
-- Run once to set up the database:
--   mysql -u root -p < schema.sql
-- ──────────────────────────────────────────────────────────────────────────────

CREATE DATABASE IF NOT EXISTS fika_loans CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE fika_loans;

-- Users (customers & admins)
CREATE TABLE IF NOT EXISTS users (
  id            INT           AUTO_INCREMENT PRIMARY KEY,
  full_name     VARCHAR(120)  NOT NULL,
  phone         VARCHAR(20)   NOT NULL UNIQUE,
  email         VARCHAR(120)  NOT NULL UNIQUE,
  national_id   VARCHAR(30)   NOT NULL UNIQUE,
  password_hash VARCHAR(255)  NOT NULL,
  role          ENUM('customer','admin') DEFAULT 'customer',
  created_at    TIMESTAMP     DEFAULT CURRENT_TIMESTAMP
);

-- Loan applications
CREATE TABLE IF NOT EXISTS loans (
  id                   INT          AUTO_INCREMENT PRIMARY KEY,
  user_id              INT          NOT NULL,
  principal            DECIMAL(12,2) NOT NULL,
  term_months          TINYINT      NOT NULL,
  interest_rate        DECIMAL(5,4) NOT NULL,
  total_payable        DECIMAL(12,2) NOT NULL,
  monthly_installment  DECIMAL(12,2) NOT NULL,
  amount_paid          DECIMAL(12,2) DEFAULT 0.00,
  purpose              VARCHAR(160),
  status               ENUM('pending','active','rejected','paid') DEFAULT 'pending',
  created_at           TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
  disbursed_at         DATETIME     NULL,
  FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE,
  INDEX idx_user   (user_id),
  INDEX idx_status (status)
);

-- Individual repayment transactions
CREATE TABLE IF NOT EXISTS repayments (
  id        INT           AUTO_INCREMENT PRIMARY KEY,
  loan_id   INT           NOT NULL,
  amount    DECIMAL(12,2) NOT NULL,
  paid_at   TIMESTAMP     DEFAULT CURRENT_TIMESTAMP,
  FOREIGN KEY (loan_id) REFERENCES loans(id) ON DELETE CASCADE
);
