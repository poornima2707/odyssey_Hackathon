# 🤖 AI-Powered RFP Analysis Platform

## 📌 Problem Statement

Manual analysis of **Request for Proposal (RFP)** documents for compliance and contractual risk assessment is a **time-consuming** and **error-prone** process. Given the **volume, variability, and complexity** of RFPs, traditional methods often lead to **human oversight** and inefficiencies in decision-making.

To address this, an **AI-driven solution** was implemented that automates RFP analysis using **Generative AI**, **Retrieval-Augmented Generation (RAG)**, and **agentic workflows**. This significantly improves the **accuracy, speed, and consistency** of compliance checks and risk evaluations.

---

## 📖 Overview

This system streamlines RFP processing by:
- Automating standard compliance checks.
- Extracting mandatory eligibility criteria.
- Generating a structured submission checklist.
- Analyzing contract clauses for risk.

The solution ingests RFPs in various formats (PDFs, DOCX, etc.) and outputs a **summary report** (JSON + PDF) with actionable insights using large language models.

---

## ✨ Features

### ✅ Automating Standard Compliance Checks
- Validates if **ConsultAdd** is legally eligible to bid (e.g., state registration, certifications, past performance).
- Identifies deal-breaker clauses early in the pipeline.

### 🧾 Extracting Mandatory Eligibility Criteria
- Extracts key **qualifications, certifications, and required experience**.
- Flags **missing criteria** to avoid unnecessary effort on non-qualifying bids.

### 📋 Generating a Submission Checklist
- Parses submission rules including:
  - Page limits, font style/size, spacing.
  - Mandatory forms and attachments.
  - TOC and section ordering requirements.

### ⚖️ Analyzing Contract Risks
- Detects **biased or one-sided legal clauses** (e.g., unilateral termination).
- Recommends more balanced terms (e.g., mutual notice periods, revision of penalty clauses).

---

## 🧰 Tech Stack

| Layer | Technologies |
|-------|--------------|
| **Frontend** | React, TailwindCSS, HTML |
| **Backend** | Flask, FastAPI |
| **AI / LLM** | Groq AI API, LangChain, Agentic Workflows |
| **Data Parsing** | DocumentParser, RecursiveTextSplitter, NumPy |
| **Templating** | Jinja2 |
| **PDF Rendering** | pdfkit, wkhtmltopdf |
| **Storage & Env** | JSON, dotenv |

---

## 🏗️ Architecture

![WhatsApp Image 2025-04-06 at 17 22 34_6d1a6f5e](https://github.com/user-attachments/assets/5cc44b47-4218-43e4-97af-68571f8a802d)
