# Automation Setup: Running the V3 Intelligence Scanner Overnight

Because the V3 Ultimate Intelligence Scanner uses a headless Chrome browser to dynamically extract documents from hundreds of municipal portals and feeds them through the Gemini AI model, **a full province-wide scan will take several hours.**

To make this invisible to you, you should set it up to run automatically every night using **Windows Task Scheduler**. By the time you log in at 7:00 AM, the new intelligence will be waiting for you in your inbox and on the Streamlit dashboard!

## Step 1: Create a Batch File (.bat)
First, you need a single executable file that runs all the required Python scripts in order.
1. Open Notepad.
2. Paste the following text into it (make sure to replace `YOUR_API_KEY_HERE` with your actual Google Gemini API key):

```bat
@echo off
echo Starting OFA Municipal Intelligence Overnight Run...

:: 1. Set environment variables for the session
set GEMINI_API_KEY=YOUR_API_KEY_HERE
set SMTP_USER=your_email@ofa.on.ca
set SMTP_PASS=your_email_password
set EMAIL_TO=your_email@ofa.on.ca

:: Navigate to your project folder
cd /d "C:\Users\ben.lefort\OneDrive - Ontario Federation of Agriculture\Desktop\Municipal Bylaw Database\Data Pulls\Reports\Province Wide\All bylaws\county-bylaw-maps"

:: 2. Run the Deep Crawler (This will take hours)
python scanner_v3_spider.py

:: 3. Generate the master signals.csv database
python generate_signals.py

:: 4. Send the Morning Briefing Email
python email_reporter.py

echo Overnight Run Complete!
```

3. Save this file on your Desktop or in the project folder as `Run_Overnight_Scanner.bat`.

## Step 2: Set up Windows Task Scheduler
Now, tell Windows to run that `.bat` file automatically for you every Monday.

1. Click the Windows Start menu and type **Task Scheduler**, then open it.
2. In the right-hand panel, click **Create Basic Task...**
3. **Name:** Enter "OFA Weekly Bylaw Intelligence Scanner" and click Next.
4. **Trigger:** Choose **Weekly** and click Next.
5. **Time:** Set the start time to **12:00:00 PM**. Ensure "Recur every 1 weeks on:" is checked for **Monday**. Click Next.
6. **Action:** Choose **Start a program** and click Next.
7. **Program/script:** Click "Browse..." and select the `Run_Overnight_Scanner.bat` file you created in Step 1.
8. Click **Finish**.

## Step 3: Run with Highest Privileges (Important!)
To make sure the script runs smoothly in the background without getting blocked by Windows:
1. In Task Scheduler, find your new task in the middle list ("OFA Nightly Bylaw Intelligence Scanner").
2. Right-click it and select **Properties**.
3. On the General tab, check the box that says **"Run with highest privileges"**.
4. Check **"Run whether user is logged on or not"** (You will have to enter your Windows password to confirm).
5. Click OK.

**You're done!** 
The system will now autonomously scrape the web, read the PDFs using AI, update your Streamlit database, and email you a briefing report every night at 2:00 AM.
