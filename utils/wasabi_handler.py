import boto3
import os
import yaml
from botocore.exceptions import NoCredentialsError

# === CONFIG ===
def load_config():
    config_path = os.path.expanduser('~/quantumdev-open/config/wasabi_settings.yaml')
    with open(config_path) as f:
        config = yaml.safe_load(f)['wasabi']
    return config

config = load_config()

s3 = boto3.client(
    's3',
    endpoint_url=f'https://s3.{config["region"]}.wasabisys.com',
    aws_access_key_id=config['access_key'],
    aws_secret_access_key=config['secret_key']
)

bucket_name = config['bucket']

# === FUNZIONI BASE ===

def upload_file(local_path, s3_path):
    try:
        s3.upload_file(local_path, bucket_name, s3_path)
        print(f"✅ Upload: {local_path} → {s3_path}")
    except Exception as e:
        print(f"❌ Errore upload file: {e}")

def download_file(s3_path, local_path):
    try:
        s3.download_file(bucket_name, s3_path, local_path)
        print(f"✅ Download: {s3_path} → {local_path}")
    except Exception as e:
        print(f"❌ Errore download file: {e}")

def list_bucket(prefix=""):
    try:
        response = s3.list_objects_v2(Bucket=bucket_name, Prefix=prefix)
        return [item['Key'] for item in response.get('Contents', [])]
    except Exception as e:
        print(f"❌ Errore lista: {e}")
        return []

# === GESTIONE CARTELLE ===

def upload_folder(folder_path, s3_prefix=""):
    for root, dirs, files in os.walk(folder_path):
        for file in files:
            local_path = os.path.join(root, file)
            relative_path = os.path.relpath(local_path, folder_path)
            s3_path = os.path.join(s3_prefix, relative_path).replace("\\", "/")
            upload_file(local_path, s3_path)

def download_folder(s3_prefix, local_folder):
    os.makedirs(local_folder, exist_ok=True)
    for key in list_bucket(s3_prefix):
        filename = os.path.basename(key)
        local_path = os.path.join(local_folder, filename)
        download_file(key, local_path)

# === FUNZIONI AVANZATE ===

def check_file_exists(s3_path):
    try:
        s3.head_object(Bucket=bucket_name, Key=s3_path)
        return True
    except:
        return False

def delete_file(s3_path):
    try:
        s3.delete_object(Bucket=bucket_name, Key=s3_path)
        print(f"🗑️ File eliminato: {s3_path}")
    except Exception as e:
        print(f"❌ Errore eliminazione file: {e}")

def delete_prefix(prefix):
    try:
        objects = [{'Key': key} for key in list_bucket(prefix)]
        if objects:
            s3.delete_objects(Bucket=bucket_name, Delete={'Objects': objects})
            print(f"🗑️ Eliminati tutti i file sotto: {prefix}")
    except Exception as e:
        print(f"❌ Errore eliminazione cartella: {e}")
