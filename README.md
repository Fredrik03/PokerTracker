# Poker Tracker

A lightweight web application for tracking your home-game poker sessions. Log every buy-in and cash-out, then explore:

- **Personal Dashboard**: See total sessions, net profit/loss, average profit, and win rate.  
- **Monthly & Global Stats**: Identify this month’s top earner/loser, view all-time leaderboards, plus charts of cumulative balances.  
- **Game History**: Browse every session by date, winner, and amount won/lost.  
- **Responsive UI**: Built with FastAPI, Jinja2, Chart.js and TailwindCSS for a clean, mobile-friendly experience.

### Features

- **User authentication** (including forced initial password set by admins)  
- **Real-time charts** powered by Chart.js  
- **Role-based admin panel** for managing players  
- **SQLite backend** for simple, zero-config storage  

### Tech Stack

- **Backend**: [FastAPI](https://fastapi.tiangolo.com/)  
- **Templates**: Jinja2  
- **Styling**: TailwindCSS + Flowbite  
- **Charts**: Chart.js  
- **Auth**: Session-based with Passlib/Bcrypt  
- **Database**: SQLite  

### Getting Started

1. **Clone** the repo:  
   ```bash
   git clone https://github.com/your-username/poker-tracker.git
   cd poker-tracker
