FROM ubuntu:20.04

WORKDIR /home/algo
COPY src /home/algo

RUN apt-get update
RUN apt-get install -y gnupg2 curl software-properties-common lsof
RUN curl -O https://releases.algorand.com/key.pub
RUN apt-key add key.pub
RUN add-apt-repository "deb [arch=amd64] https://releases.algorand.com/deb/ stable main"
RUN apt-get update
RUN apt-get install -y algorand
RUN apt-get clean
RUN algod -v && ls -la /home/algo

EXPOSE 8080

CMD chmod +x init.sh && ./init.sh
