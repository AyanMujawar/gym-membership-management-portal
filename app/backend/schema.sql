CREATE DATABASE IF NOT EXISTS gym_portal;
USE gym_portal;

CREATE TABLE admins (
    admin_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL
);

CREATE TABLE users (
    user_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    email VARCHAR(100) UNIQUE NOT NULL,
    password VARCHAR(255) NOT NULL,
    phone VARCHAR(15),
    address VARCHAR(255),
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE membership_plans (
    plan_id INT AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(50) NOT NULL,
    duration_days INT NOT NULL,
    price DECIMAL(10,2) NOT NULL,
    description VARCHAR(255),
    is_active BOOLEAN DEFAULT TRUE
);

-- start_date / end_date stay NULL while a membership is Pending; the admin's
-- approval sets them (and flips the status to Active).
CREATE TABLE memberships (
    membership_id INT AUTO_INCREMENT PRIMARY KEY,
    user_id INT NOT NULL,
    plan_id INT NOT NULL,
    start_date DATE,
    end_date DATE,
    status ENUM('Pending','Active','Expired','Rejected') DEFAULT 'Pending',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id),
    FOREIGN KEY (plan_id) REFERENCES membership_plans(plan_id)
);

-- Payments are simulated: no real gateway, a row is just recorded when the member "pays".
CREATE TABLE payments (
    payment_id INT AUTO_INCREMENT PRIMARY KEY,
    membership_id INT NOT NULL,
    user_id INT NOT NULL,
    amount DECIMAL(10,2) NOT NULL,
    method ENUM('Card','UPI','NetBanking') NOT NULL,
    status ENUM('Paid','Refunded') DEFAULT 'Paid',
    txn_ref VARCHAR(30) NOT NULL,
    payment_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (membership_id) REFERENCES memberships(membership_id),
    FOREIGN KEY (user_id) REFERENCES users(user_id)
);

-- Seed data so every fresh environment (a teammate's laptop, a redeployed
-- AWS server) shows a working demo immediately instead of empty screens.
-- Admin login:  admin@gym.com  / Admin@123
-- Members (all use the password Member@123):
--   demo@member.com     active Quarterly plan        priya@member.com   active Yearly (renewed earlier)
--   arjun@member.com    active Half-Yearly           sneha@member.com   active Monthly, expires in 6 days
--   expired@member.com  Monthly expired 15 days ago  vikram@member.com  Quarterly expired 40 days ago
--   neha@member.com     payment made, PENDING approval (approve it in the admin dashboard)
--   rohan@member.com    registered, no membership yet
INSERT INTO admins (name, email, password) VALUES
('Gym Admin', 'admin@gym.com', 'scrypt:32768:8:1$MfQIfNFt8K8vyuYz$1e8868321fab1a818d8e8ef2efa1bef7f480f7b54934ad23dd3b9537f84840873d9006caeae7330e6de862798fdaa5e7f3e65c622a891832f81fa995a729a41e');

INSERT INTO membership_plans (name, duration_days, price, description) VALUES
('Monthly', 30, 1000.00, 'Full gym access for 30 days'),
('Quarterly', 90, 2700.00, 'Full gym access for 3 months - save 10%'),
('Half-Yearly', 180, 5000.00, 'Full gym access for 6 months plus 1 free trainer session'),
('Yearly', 365, 9000.00, 'Best value - full access for a year plus a diet consultation');

INSERT INTO users (name, email, password, phone, address) VALUES
('Demo Member', 'demo@member.com', 'scrypt:32768:8:1$yzVhCEJCvALD8OmT$718a4bd0eb4f81a2da14b43f96cf603f46afc25adfa74872938e835069a2bcd46a4d2c39215dac654e85401dbd6c00680b859413f6a7d6ef5edb840b377eeb49', '9876543210', 'Pune, Maharashtra'),
('Rahul Sharma', 'expired@member.com', 'scrypt:32768:8:1$yzVhCEJCvALD8OmT$718a4bd0eb4f81a2da14b43f96cf603f46afc25adfa74872938e835069a2bcd46a4d2c39215dac654e85401dbd6c00680b859413f6a7d6ef5edb840b377eeb49', '9123456780', 'Mumbai, Maharashtra'),
('Priya Nair', 'priya@member.com', 'scrypt:32768:8:1$yzVhCEJCvALD8OmT$718a4bd0eb4f81a2da14b43f96cf603f46afc25adfa74872938e835069a2bcd46a4d2c39215dac654e85401dbd6c00680b859413f6a7d6ef5edb840b377eeb49', '9822011122', 'Kothrud, Pune'),
('Arjun Mehta', 'arjun@member.com', 'scrypt:32768:8:1$yzVhCEJCvALD8OmT$718a4bd0eb4f81a2da14b43f96cf603f46afc25adfa74872938e835069a2bcd46a4d2c39215dac654e85401dbd6c00680b859413f6a7d6ef5edb840b377eeb49', '9822033344', 'Baner, Pune'),
('Sneha Kulkarni', 'sneha@member.com', 'scrypt:32768:8:1$yzVhCEJCvALD8OmT$718a4bd0eb4f81a2da14b43f96cf603f46afc25adfa74872938e835069a2bcd46a4d2c39215dac654e85401dbd6c00680b859413f6a7d6ef5edb840b377eeb49', '9822055566', 'Aundh, Pune'),
('Vikram Patil', 'vikram@member.com', 'scrypt:32768:8:1$yzVhCEJCvALD8OmT$718a4bd0eb4f81a2da14b43f96cf603f46afc25adfa74872938e835069a2bcd46a4d2c39215dac654e85401dbd6c00680b859413f6a7d6ef5edb840b377eeb49', '9822077788', 'Hadapsar, Pune'),
('Neha Joshi', 'neha@member.com', 'scrypt:32768:8:1$yzVhCEJCvALD8OmT$718a4bd0eb4f81a2da14b43f96cf603f46afc25adfa74872938e835069a2bcd46a4d2c39215dac654e85401dbd6c00680b859413f6a7d6ef5edb840b377eeb49', '9822099900', 'Wakad, Pune'),
('Rohan Desai', 'rohan@member.com', 'scrypt:32768:8:1$yzVhCEJCvALD8OmT$718a4bd0eb4f81a2da14b43f96cf603f46afc25adfa74872938e835069a2bcd46a4d2c39215dac654e85401dbd6c00680b859413f6a7d6ef5edb840b377eeb49', '9822000011', 'Viman Nagar, Pune');

-- Dates are relative to the day the database is first created, so the demo always looks current
INSERT INTO memberships (user_id, plan_id, start_date, end_date, status) VALUES
(1, 2, DATE_SUB(CURDATE(), INTERVAL 2 DAY), DATE_ADD(CURDATE(), INTERVAL 88 DAY), 'Active'),
(2, 1, DATE_SUB(CURDATE(), INTERVAL 45 DAY), DATE_SUB(CURDATE(), INTERVAL 15 DAY), 'Expired'),
(3, 4, DATE_SUB(CURDATE(), INTERVAL 100 DAY), DATE_ADD(CURDATE(), INTERVAL 265 DAY), 'Active'),
(4, 3, DATE_SUB(CURDATE(), INTERVAL 60 DAY), DATE_ADD(CURDATE(), INTERVAL 120 DAY), 'Active'),
(5, 1, DATE_SUB(CURDATE(), INTERVAL 24 DAY), DATE_ADD(CURDATE(), INTERVAL 6 DAY), 'Active'),
(6, 2, DATE_SUB(CURDATE(), INTERVAL 130 DAY), DATE_SUB(CURDATE(), INTERVAL 40 DAY), 'Expired'),
(7, 1, NULL, NULL, 'Pending'),
(3, 1, DATE_SUB(CURDATE(), INTERVAL 140 DAY), DATE_SUB(CURDATE(), INTERVAL 110 DAY), 'Expired');

INSERT INTO payments (membership_id, user_id, amount, method, status, txn_ref, payment_date) VALUES
(1, 1, 2700.00, 'UPI', 'Paid', 'TXNSEED0001', DATE_SUB(NOW(), INTERVAL 2 DAY)),
(2, 2, 1000.00, 'Card', 'Paid', 'TXNSEED0002', DATE_SUB(NOW(), INTERVAL 45 DAY)),
(3, 3, 9000.00, 'NetBanking', 'Paid', 'TXNSEED0003', DATE_SUB(NOW(), INTERVAL 100 DAY)),
(4, 4, 5000.00, 'UPI', 'Paid', 'TXNSEED0004', DATE_SUB(NOW(), INTERVAL 60 DAY)),
(5, 5, 1000.00, 'Card', 'Paid', 'TXNSEED0005', DATE_SUB(NOW(), INTERVAL 24 DAY)),
(6, 6, 2700.00, 'UPI', 'Paid', 'TXNSEED0006', DATE_SUB(NOW(), INTERVAL 130 DAY)),
(7, 7, 1000.00, 'UPI', 'Paid', 'TXNSEED0007', DATE_SUB(NOW(), INTERVAL 1 DAY)),
(8, 3, 1000.00, 'Card', 'Paid', 'TXNSEED0008', DATE_SUB(NOW(), INTERVAL 140 DAY));
