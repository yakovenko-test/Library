// Параметризованный скрипт инициализации MongoDB
// Количество записей берется из переменной окружения MONGO_RECORDS_COUNT
// По умолчанию 100000

db = db.getSiblingDB("benchmark");

var recordsCount = parseInt(process.env.MONGO_RECORDS_COUNT || "100000");
print("Инициализация MongoDB с " + recordsCount + " записями...");

db.users.drop();

var bulk = db.users.initializeUnorderedBulkOp();
var batchSize = 1000;

for (var i = 1; i <= recordsCount; i++) {
  bulk.insert({
    _id: i,
    name: "User " + i,
    email: "user" + i + "@example.com",
    created_at: new Date(Date.now() - Math.random() * 365 * 24 * 60 * 60 * 1000),
    last_login_at: new Date(Date.now() - Math.random() * 365 * 24 * 60 * 60 * 1000),
  });

  if (i % batchSize === 0) {
    bulk.execute();
    bulk = db.users.initializeUnorderedBulkOp();
  }
}

// выполнить "хвост" батча, если он есть
try {
  bulk.execute();
} catch (e) {
  // может быть пустым, тогда ошибка "Invalid Operation" – игнорируем
}

db.users.createIndex({ email: 1 }, { unique: true });
db.users.createIndex({ last_login_at: 1 });

var count = db.users.count();
print("Инициализация завершена. Записей в коллекции: " + count);




