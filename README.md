# MindBuilding - Automated Building Maintenance System

A full-stack solution for streamlined building management, featuring an automated WhatsApp chatbot for incident reporting and a high-end Admin Dashboard for real-time tracking.

## System Showcase
*(Replace placeholders with your screenshots/GIFs)*

| Admin Login | Management Dashboard | WhatsApp Bot Flow |
| :---: | :---: | :---: |
| <img src="https://github.com/user-attachments/assets/a6a70b9c-af8d-4cc0-b931-7789a7689973" width="200"> | <img src="https://github.com/user-attachments/assets/fc74facc-abbb-499e-9a5d-d9c58e4d09fb" width="200"> | ![Bot Demo](screenshots/bot_demo.gif) |

##  Key Features

- **Conversational Reporting:** Structured WhatsApp flow that handles location, unit details, and issue descriptions.
- **Dynamic Dashboard:** A secure, responsive web interface for property managers to oversee all active reports.
- **Status Lifecycle:** Interactive controls to update reports from 'Pending' to 'In Progress' or 'Resolved'.
- **Database Persistence:** Fully integrated with PostgreSQL for reliable data logging and retrieval.
- **Containerized Architecture:** Built with Docker for seamless deployment and scalability.

##  Tech Stack
- **Backend:** Python (FastAPI, Uvicorn)
- **Database:** PostgreSQL (Supabase)
- **API Integration:** WhatsApp Business Cloud API (Meta)
- **DevOps:** Docker, GitHub Actions, Render
- **Frontend:** Modern CSS3 & HTML5 (Responsive Design)

##  Quick Start (Docker)
This project is fully containerized. To run the entire environment locally:

1. **Build the image:**
   ```bash
   docker build -t mindbuilding-app .
