# This Dockerfile only installs requirements. App has to be mounted later
FROM python:3.9
WORKDIR /app
COPY requirements.txt
RUN pip3 install -r requirements.txt
COPY . .
CMD [ "python", "./fistop.py"]
EXPOSE 80 443