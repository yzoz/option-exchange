// Сервис каталога инструментов (задача ТЗ #23).
//
// Раньше чтение и разбор exchange/instruments.json были инлайн в routes/exchange.js
// (глобалы, чтение файла на каждый запрос, дублирование обхода вложенной структуры).
// Теперь это отдельный модуль-сервис: путь к файлу разрешается от корня репозитория,
// поэтому он не зависит от текущего каталога запуска. Роутеры занимаются только HTTP.
//
// Структура файла (см. DEVELOPER_GUIDE §4.2):
//   [ { "ETH_BTC": { name, size, measure, series: [ { "<exp>": { strikes: [...] } } ] } } ]

var fs = require('fs')
var path = require('path')

var INSTRUMENTS = path.join(__dirname, '..', 'exchange', 'instruments.json')

function load() {
	// Читаем на каждый вызов, не кэшируем: правка instruments.json должна
	// подхватываться без перезапуска веб-слоя (см. DONE #17).
	return JSON.parse(fs.readFileSync(INSTRUMENTS, 'utf8'))
}

// Найти тикер (напр. ETH_BTC) в каталоге. Возвращает запись инструмента или null.
function instrument(ticker) {
	var instruments = load()
	for (var i = 0; i < instruments.length; i++) {
		if (instruments[i][ticker]) {
			return instruments[i][ticker]
		}
	}
	return null
}

// Ближайшая (первая в файле) серия тикера — на неё редиректит GET /exchange/.
function firstExp(ticker) {
	var ass = instrument(ticker)
	if (!ass || !ass.series || !ass.series.length) {
		return null
	}
	return Object.keys(ass.series[0])[0]
}

// Серия тикера по exp (unix-сек). Возвращает метаданные инструмента и страйки.
function series(ticker, exp) {
	var ass = instrument(ticker)
	if (!ass) {
		return null
	}
	for (var s = 0; s < ass.series.length; s++) {
		if (ass.series[s][exp]) {
			return {
				name: ass.name,
				size: ass.size,
				measure: ass.measure,
				strikes: ass.series[s][exp].strikes
			}
		}
	}
	return null
}

module.exports = {
	INSTRUMENTS: INSTRUMENTS,
	load: load,
	instrument: instrument,
	firstExp: firstExp,
	series: series
}
