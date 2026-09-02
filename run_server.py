import sys
import os
import uvicorn

def main():
    use_http = "--http" in sys.argv
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cert_file = os.path.join(base_dir, "cert.pem")
    key_file = os.path.join(base_dir, "key.pem")

    local_ip = "10.21.233.180"

    print("==========================================================")
    print("   Pi Jam Classroom Assessment Web Application Server   ")
    print("==========================================================")

    if not use_http and os.path.exists(cert_file) and os.path.exists(key_file):
        print(f"[*] Starting with HTTPS (Required for Mobile Camera Access)")
        print(f"[*] Access from Laptop: https://localhost:8000")
        print(f"[*] Access from Mobile: https://{local_ip}:8000")
        print("----------------------------------------------------------")
        print("NOTE for Mobile Browser: Tap 'Advanced' -> 'Proceed' to accept")
        print("the local self-signed certificate.")
        print("==========================================================")
        uvicorn.run(
            "backend.main:app",
            host="0.0.0.0",
            port=8000,
            ssl_keyfile=key_file,
            ssl_certfile=cert_file,
            reload=False
        )
    else:
        print(f"[*] Starting with HTTP")
        print(f"[*] Access from Laptop: http://localhost:8000")
        print(f"[*] Access from Mobile: http://{local_ip}:8000")
        print("==========================================================")
        uvicorn.run(
            "backend.main:app",
            host="0.0.0.0",
            port=8000,
            reload=False
        )

if __name__ == "__main__":
    main()
