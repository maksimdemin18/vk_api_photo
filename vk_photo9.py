#!/usr/bin/env python3
import os
import requests
import json
import yaml
from datetime import datetime
from tqdm import tqdm
import logging

VK_API_URL = 'https://api.vk.com/method'
VK_API_VERSION = '5.131'
BASE_FOLDER = 'vk_photos_backup'

logging.basicConfig(filename='vk_backup.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

class VKAPI:
    def __init__(self, access_token):
        self.session = requests.Session()
        self.access_token = access_token
        self.params = {
            'v': VK_API_VERSION,
            'access_token': self.access_token
        }

    def get_friends(self):
        params = {
            **self.params,
            'order': 'name',
            'fields': 'id,first_name,last_name'
        }
        try:
            response = self.session.get(f'{VK_API_URL}/friends.get', params=params)
            response.raise_for_status()
            data = response.json()
            if 'error' in data:
                raise Exception(f"Ошибка VK API: {data['error']['error_msg']}")
            return data['response']['items']
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка при запросе к VK API: {e}")
            raise

    def get_photos(self, user_id, album_id='profile', count=5):
        params = {
            **self.params,
            'owner_id': user_id,
            'album_id': album_id,
            'extended': 1,
            'photo_sizes': 1,
            'count': count
        }
        try:
            response = self.session.get(f'{VK_API_URL}/photos.get', params=params)
            response.raise_for_status()
            data = response.json()
            if 'error' in data:
                raise Exception(f"Ошибка VK API: {data['error']['error_msg']}")
            return data['response']['items']
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка при запросе к VK API: {e}")
            raise

    def get_all_photos(self, user_id, album_id='profile'):
        params = {
            **self.params,
            'owner_id': user_id,
            'album_id': album_id,
            'extended': 1,
            'photo_sizes': 1,
            'count': 1000
        }
        all_photos = []
        offset = 0
        
        while True:
            try:
                params['offset'] = offset
                response = self.session.get(f'{VK_API_URL}/photos.get', params=params)
                response.raise_for_status()
                data = response.json()
                if 'error' in data:
                    if data['error']['error_code'] == 200:
                        logging.warning(f"Нет доступа к альбому {album_id} пользователя {user_id}")
                        return []
                    else:
                        raise Exception(f"Ошибка VK API: {data['error']['error_msg']}")
                
                photos = data['response']['items']
                all_photos.extend(photos)
                
                if len(photos) < params['count']:
                    break
                
                offset += len(photos)
            except requests.exceptions.RequestException as e:
                logging.error(f"Ошибка при запросе к VK API: {e}")
                raise
        
        return all_photos

    def get_albums(self, user_id):
        params = {
            **self.params,
            'owner_id': user_id,
            'need_system': 1
        }
        try:
            response = self.session.get(f'{VK_API_URL}/photos.getAlbums', params=params)
            response.raise_for_status()
            data = response.json()
            if 'error' in data:
                raise Exception(f"Ошибка VK API: {data['error']['error_msg']}")
            return data['response']['items']
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка при запросе к VK API: {e}")
            raise

    def check_album_access(self, user_id, album_id):
        params = {
            **self.params,
            'owner_id': user_id,
            'album_ids': album_id
        }
        try:
            response = self.session.get(f'{VK_API_URL}/photos.getAlbums', params=params)
            response.raise_for_status()
            data = response.json()
            if 'error' in data:
                if data['error']['error_code'] == 200:
                    return False
                else:
                    raise Exception(f"Ошибка VK API: {data['error']['error_msg']}")
            return len(data['response']['items']) > 0
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка при проверке доступа к альбому: {e}")
            return False

class YandexDiskAPI:
    def __init__(self, token):
        self.session = requests.Session()
        self.session.headers.update({'Authorization': f'OAuth {token}'})

    def create_folder(self, folder_path):
        params = {'path': folder_path}
        try:
            response = self.session.put('https://cloud-api.yandex.net/v1/disk/resources', params=params)
            if response.status_code == 201:
                logging.info(f"Папка {folder_path} успешно создана")
            elif response.status_code == 409:
                logging.info(f"Папка {folder_path} уже существует")
            else:
                response.raise_for_status()
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка при работе с папкой {folder_path} на Яндекс.Диске: {e}")
            raise

    def upload_photo(self, photo_url, file_name, folder_path):
        params = {'path': f'{folder_path}/{file_name}', 'url': photo_url}
        try:
            response = self.session.post('https://cloud-api.yandex.net/v1/disk/resources/upload', params=params)
            response.raise_for_status()
            logging.info(f"Файл {file_name} успешно загружен")
            return True
        except requests.exceptions.RequestException as e:
            logging.error(f"Ошибка при загрузке файла {file_name}: {e}")
            return False

class ConfigLoader:
    @staticmethod
    def load_config():
        try:
            with open('config.yaml', 'r', encoding='utf-8') as f:
                config = yaml.safe_load(f)
            
            if 'vk_token' not in config or 'ya_token' not in config:
                raise KeyError("В конфигурационном файле отсутствуют необходимые ключи")
            
            if not config['vk_token'] or not config['ya_token']:
                raise ValueError("Токены VK или Яндекс.Диска не могут быть пустыми")
            
            return config
        except (FileNotFoundError, yaml.YAMLError, KeyError, ValueError) as e:
            logging.error(f"Ошибка при загрузке конфигурации: {e}")
            raise

class PhotoSaver:
    @staticmethod
    def save_photo_locally(photo_url, file_name, folder_path):
        try:
            if not os.path.exists(folder_path):
                os.makedirs(folder_path)
            
            response = requests.get(photo_url)
            response.raise_for_status()
            
            file_path = os.path.join(folder_path, file_name)
            with open(file_path, 'wb') as f:
                f.write(response.content)
            
            logging.info(f"Файл {file_name} успешно сохранен локально")
            return True
        except Exception as e:
            logging.error(f"Ошибка при сохранении файла {file_name} локально: {e}")
            return False

    @staticmethod
    def get_largest_size(sizes):
        return max(sizes, key=lambda x: x['width'] * x['height'])

class PhotoProcessor:
    def __init__(self, vk_api, yandex_disk_api):
        self.vk_api = vk_api
        self.yandex_disk_api = yandex_disk_api

    def process_user(self, user_id):
        print("\nВыберите источник фотографий:")
        print("1. Фотографии профиля")
        print("2. Фотографии со стены")
        print("3. Фотографии из альбома")
        
        while True:
            source_choice = input("Введите номер источника (1, 2 или 3): ")
            if source_choice in ['1', '2', '3']:
                break
            print("Неверный выбор. Попробуйте еще раз.")
        
        if source_choice == '1':
            album_id = 'profile'
        elif source_choice == '2':
            album_id = 'wall'
        else:
            albums = self.vk_api.get_albums(user_id)
            print("\nСписок альбомов:")
            for i, album in enumerate(albums, start=1):
                print(f"{i}. {album['title']} (ID: {album['id']})")
            
            while True:
                try:
                    album_choice = int(input("Введите номер альбома: "))
                    if 1 <= album_choice <= len(albums):
                        album_id = albums[album_choice - 1]['id']
                        break
                    else:
                        print("Неверный выбор. Попробуйте еще раз.")
                except ValueError:
                    print("Неверный ввод. Пожалуйста, введите число.")

        if album_id != 'profile' and album_id != 'wall':
            if not self.vk_api.check_album_access(user_id, album_id):
                print(f"У вас нет доступа к выбранному альбому. Пожалуйста, выберите другой альбом или источник фотографий.")
                return

        while True:
            save_choice = input("Выберите место сохранения (1 - Локально, 2 - Яндекс.Диск): ")
            if save_choice in ['1', '2']:
                break
            print("Неверный выбор. Попробуйте еще раз.")
        
        save_locally = save_choice == '1'
        
        while True:
            photo_choice = input("Выберите количество фотографий (1 - Все фото, 2 - Топ-5 по лайкам): ")
            if photo_choice in ['1', '2']:
                break
            print("Неверный выбор. Попробуйте еще раз.")
        
        save_all_photos = photo_choice == '1'
        
        if save_all_photos:
            photos = self.vk_api.get_all_photos(user_id, album_id)
        else:
            photos = self.vk_api.get_photos(user_id, album_id, count=5)
        
        if not photos:
            print(f"Не удалось получить фотографии из выбранного источника. Возможно, альбом пуст или у вас нет доступа.")
            return

        if not save_locally:
            try:
                self.yandex_disk_api.create_folder(BASE_FOLDER)
                user_folder = f'{BASE_FOLDER}/{user_id}'
                self.yandex_disk_api.create_folder(user_folder)
            except Exception as e:
                logging.error(f"Ошибка при создании папок на Яндекс.Диске: {e}")
                raise
        else:
            user_folder = f'local_backup/{user_id}'
        
        saved_photos = []
        for photo in tqdm(photos, desc="Сохранение фотографий"):
            largest = PhotoSaver.get_largest_size(photo['sizes'])
            file_name = f"{photo['likes']['count']}_{datetime.fromtimestamp(photo['date']).strftime('%Y-%m-%d')}.jpg"
            
            if save_locally:
                success = PhotoSaver.save_photo_locally(largest['url'], file_name, user_folder)
            else:
                success = self.yandex_disk_api.upload_photo(largest['url'], file_name, user_folder)
            
            if success:
                saved_photos.append({
                    "file_name": file_name,
                    "size": largest['type'],
                    "width": largest['width'],
                    "height": largest['height']
                })
        
        with open(f'photos_info_{user_id}.json', 'w', encoding='utf-8') as f:
            json.dump(saved_photos, f, ensure_ascii=False, indent=2)
        
        print(f"Сохранено {len(saved_photos)} фотографий. Информация сохранена в файле photos_info_{user_id}.json")
        if save_locally:
            print(f"Фотографии сохранены локально в папке: {os.path.abspath(user_folder)}")
        else:
            print(f"Фотографии загружены на Яндекс.Диск в папку: {user_folder}")

class VKPhotoBackup:
    def __init__(self):
        self.config = ConfigLoader.load_config()
        self.vk_api = VKAPI(self.config['vk_token'])
        self.yandex_disk_api = YandexDiskAPI(self.config['ya_token'])
        self.photo_processor = PhotoProcessor(self.vk_api, self.yandex_disk_api)

    def run(self):
        logging.info("Начало выполнения программы")
        
        try:
            friends = self.vk_api.get_friends()
            logging.info("VK токен успешно прошел проверку")
        except Exception as e:
            logging.error(f"Ошибка при проверке VK токена: {e}")
            raise

        while True:
            print("\nСписок ваших друзей:")
            for i, friend in enumerate(friends, start=1):
                print(f"{i}. {friend['first_name']} {friend['last_name']} (ID: {friend['id']})")
            
            print("\nВыберите действие:")
            print("1. Выбрать друга из списка")
            print("2. Использовать свой профиль")
            print("3. Ввести ID пользователя вручную")
            print("4. Выйти из программы")
            
            choice = input("Введите номер действия (1, 2, 3 или 4): ")
            
            if choice == '1':
                while True:
                    try:
                        friend_choice = int(input("Введите номер друга из списка: "))
                        if 1 <= friend_choice <= len(friends):
                            user_id = friends[friend_choice - 1]['id']
                            break
                        else:
                            print("Неверный выбор. Попробуйте еще раз.")
                    except ValueError:
                        print("Неверный ввод. Пожалуйста, введите число.")
            elif choice == '2':
                user_id = 'me'
            elif choice == '3':
                user_id = input("Введите ID пользователя VK: ")
            elif choice == '4':
                print("Выход из программы.")
                break
            else:
                print("Неверный выбор. Попробуйте еще раз.")
                continue
            
            if choice != '4':
                try:
                    self.photo_processor.process_user(user_id)
                except Exception as e:
                    print(f"Произошла ошибка при обработке пользователя: {str(e)}")
                    logging.error(f"Ошибка при обработке пользователя: {str(e)}", exc_info=True)

if __name__ == "__main__":
    try:
        vk_photo_backup = VKPhotoBackup()
        vk_photo_backup.run()
    except Exception as e:
        print(f"Произошла ошибка: {str(e)}")
        logging.error(f"Произошла ошибка: {str(e)}", exc_info=True)