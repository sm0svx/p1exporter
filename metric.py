class Metric:
    TYPE_COUNTER = "counter"
    TYPE_GAUGE = "gauge"
    
    def __init__(self, name, type_name, labels=()):
        if type(labels) != tuple:
            labels = (labels,)
        self.name = name
        self.type_name = type_name
        self.help_text = None
        self.labels = labels
        self.measurements = {}
        
    def set_type(self, type_name):
        self.type_name = type_name
        
    def set_help(self, help_text):
        self.help_text = help_text
    
    def headers(self):
        headers = ""
        if self.help_text is not None:
            headers += "# HELP " + self.name + " " + self.help_text + "\n"
        if self.type_name is not None:
            headers += "# TYPE " + self.name + " " + self.type_name + "\n"
        return headers

    def set_value(self, value, labels=(), ts=None):
        if type(value) != float:
            value = float(value)
        if type(labels) != tuple:
            labels = (labels,)
        if len(labels) != len(self.labels):
            raise Exception("Label count mismatch. Should be %d, not %d",
                            (len(self.labels), len(labels)))
        self.measurements[labels] = {
            "value": value,
            "ts" : ts
            }

    def value(self, labels=()):
        if type(labels) != tuple:
            labels = (labels,)
        if len(labels) != len(self.labels):
            raise Exception("Label count mismatch. Should be %d, not %d",
                            (len(self.labels), len(labels)))
        if labels in self.measurements:
            measurement = self.measurements[labels]
            return measurement["value"]
        
        return None
    
    def timestamp(self, labels=()):
        if type(labels) != tuple:
            labels = (labels,)
        if len(labels) != len(self.labels):
            raise Exception("Label count mismatch. Should be %d, not %d",
                            (len(self.labels), len(labels)))
        if labels in self.measurements:
            measurement = self.measurements[labels]
            if measurement["ts"] is not None:
                return int(measurement["ts"])
        return None
        
    def value_row(self, labels=()):
        if type(labels) != tuple:
            labels = (labels,)
        if len(labels) != len(self.labels):
            raise Exception("Label count mismatch. Should be %d, not %d",
                            (len(self.labels), len(labels)))
        row = self.name
        measurement = self.measurements[labels]
        if len(labels) > 0:
            row += "{"
            for i in range(0, len(labels)):
                if i > 0:
                    row += ","
                row += self.labels[i] + "=\"" + labels[i] + "\""
            row += "}"
        row += " %f" % measurement["value"]
        if measurement["ts"] is not None:
            row += " %d" % int(measurement["ts"])
        row += "\n"
        return row

    def value_rows(self):
        rows = ''
        for labels in self.measurements:
            rows += self.value_row(labels)
        return rows
    
    def lineprotocol_row(self, labels=()):
        if type(labels) != tuple:
            labels = (labels,)
        if len(labels) != len(self.labels):
            raise Exception("Label count mismatch. Should be %d, not %d",
                            (len(self.labels), len(labels)))
        row = self.name
        measurement = self.measurements[labels]
        if len(labels) > 0:
            row += ","
            for i in range(0, len(labels)):
                if i > 0:
                    row += ","
                row += self.labels[i] + "=\"" + labels[i] + "\""
        row += " _value=%f" % measurement["value"]
        if measurement["ts"] is not None:
            row += " %d000000" % int(measurement["ts"])
        row += "\n"
        return row
    
    def lineprotocol_rows(self):
        rows = ''
        for labels in self.measurements:
            rows += self.lineprotocol_row(labels)
        return rows
    
