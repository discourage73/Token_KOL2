from telethon import TelegramClient
import asyncio

api_id = 25308063
api_hash = "458e1315175e0103f19d925204b690a5"
channels = ['@CrikeyCallz',
            '@Chadleycalls',
            '@BaddiesAi']

async def main():
    # Используем другое имя сессии, чтобы избежать конфликтов
    session_name = 'get_ids_session'
    async with TelegramClient(session_name, api_id, api_hash) as client:
        print("Клиент подключен")
        channel_data = {}
        
        for channel in channels:
            try:
                entity = await client.get_entity(channel)
                channel_data[channel] = entity.id
                print(f"Канал {channel} найден: {entity.id}")
            except Exception as e:
                print(f"Ошибка при поиске канала {channel}: {e}")
        
        print("\nИспользуйте эти данные в вашем token_extractor.py:")
        print("CACHED_CHANNELS = {")
        for channel, channel_id in channel_data.items():
            channel_name = channel.replace('@', '')
            print(f'    "{channel_name}": {channel_id},')
        print("}")

if __name__ == "__main__":
    # Исправляем предупреждение о deprecated get_event_loop
    asyncio.run(main())