# Use an official lightweight Python image
FROM python:3.9-slim

# Set the working directory in the container
WORKDIR /app

# Copy the requirements file
COPY requirements.txt .

# Install the dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of your application's code
COPY . .

# Set environment variables (optional, you can also use Docker secrets or pass them at runtime)
# ENV TELEGRAM_BOT_TOKEN=your_token
# ENV OPENAI_API_KEY=your_openai_key

# Run the application
CMD ["python", "main.py"]