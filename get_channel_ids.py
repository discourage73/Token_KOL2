from telethon import TelegramClient

api_id = 25308063
api_hash = "458e1315175e0103f19d925204b690a5"
channels = ['@AlphAI_Signals_Bot']

async def main():
    async with TelegramClient('test_session', api_id, api_hash) as client:
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
    import asyncio
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())