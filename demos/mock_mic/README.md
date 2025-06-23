Trigger wakeword detection:
```bash
docker compose exec -it mock-mic python3 mock_mic/play.py ok-nabu.wav
```

Stream "What's my name?" to the server:
```bash
docker compose exec -it mock-mic python3 mock_mic/play.py whats-my-name.wav
```

Stream "What's your name?" to the server:
```bash
docker compose exec -it mock-mic python3 mock_mic/play.py whats-your-name.wav
```