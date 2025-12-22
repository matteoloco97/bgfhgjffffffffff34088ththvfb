[Service]
WorkingDirectory=/root/quantumdev-open
EnvironmentFile=/root/quantumdev-open/.env
Environment=CHROMA_PERSIST_DIR=/root/quantumdev-open/storage/chroma
Environment=EMBEDDING_MODEL_NAME=sentence-transformers/all-MiniLM-L6-v2
EOF
